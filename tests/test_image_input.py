"""Image input: the model reads an attached image into text that joins the customer's
message; everything downstream sees only text. Off unless LLM_IMAGE_INPUT is set."""
import asyncio
import base64

import httpx
import pytest

import app.routes.chat as chat_module
from app import llm_backend
from app.banking.routing import KbQuestion
from app.config import settings
from app.conversation import vision
from tests.conftest import AUTH_HEADERS
from tests.test_chat_integration_contract import _install_kb_fakes, _install_session_fakes, _parse_sse

PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
PNG_URL = f"data:image/png;base64,{PNG_B64}"


@pytest.fixture
def images_on(monkeypatch):
    monkeypatch.setattr(settings, "LLM_IMAGE_INPUT", True)


# --- decode_image ------------------------------------------------------------------


def test_decode_accepts_supported_types():
    assert vision.decode_image(PNG_URL) == PNG_B64
    assert vision.decode_image(f"data:image/jpeg;base64,{PNG_B64}") == PNG_B64


@pytest.mark.parametrize("bad", [
    "data:image/svg+xml;base64,PHN2Zz4=",       # svg: not accepted
    "data:text/plain;base64,aGVsbG8=",
    "https://example.com/cat.png",               # URLs are never fetched
    "data:image/png;base64,***not-base64***",
])
def test_decode_rejects_other_input(bad):
    with pytest.raises(vision.ImageInputError):
        vision.decode_image(bad)


def test_decode_rejects_oversized(monkeypatch):
    monkeypatch.setattr(settings, "MAX_IMAGE_MB", 1)
    big = base64.b64encode(b"0" * (1024 * 1024 + 1)).decode()
    with pytest.raises(vision.ImageInputError, match="larger than 1 MB"):
        vision.decode_image(f"data:image/png;base64,{big}")


# --- read_image ----------------------------------------------------------------------


def test_read_image_refuses_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_IMAGE_INPUT", False)
    with pytest.raises(vision.ImageInputError, match="isn't enabled"):
        asyncio.run(vision.read_image(PNG_URL, "what is this"))


def test_read_image_sends_image_and_message_to_model(images_on, monkeypatch):
    seen = {}

    async def fake_post(path, payload, *, timeout):
        seen["path"], seen["payload"] = path, payload
        return {"message": {"content": " A failed bKash transfer of Tk 5,000. "}}

    monkeypatch.setattr(vision.llm_backend, "post", fake_post)
    text = asyncio.run(vision.read_image(PNG_URL, "why did this fail?"))
    assert text == "A failed bKash transfer of Tk 5,000."
    message = seen["payload"]["messages"][0]
    assert seen["path"] == "/api/chat"
    assert message["images"] == [PNG_B64]
    assert "why did this fail?" in message["content"]
    assert "[hidden]" in message["content"]  # card numbers / PINs are never copied


def test_read_image_empty_reply_is_an_error(images_on, monkeypatch):
    async def fake_post(path, payload, *, timeout):
        return {"message": {"content": ""}}

    monkeypatch.setattr(vision.llm_backend, "post", fake_post)
    with pytest.raises(vision.ImageInputError):
        asyncio.run(vision.read_image(PNG_URL, "x"))


# --- translator: Ollama "images" -> OpenAI image_url parts ------------------------------


def test_openai_translation_sends_image_parts(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://llm/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemma4")
    body = llm_backend._to_openai("/api/chat", {"messages": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "look", "images": ["/9j/abc", PNG_B64]},
    ]})
    user = body["messages"][1]
    assert user["content"] == [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/abc"}},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG_B64}"}},
    ]


def test_merging_text_into_an_image_turn_keeps_the_image():
    merged = llm_backend._normalise_roles([
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "image_url", "image_url": {"url": "u"}}]},
        {"role": "user", "content": "b"},
    ])
    assert merged == [{"role": "user", "content": [
        {"type": "text", "text": "a"}, {"type": "image_url", "image_url": {"url": "u"}}, {"type": "text", "text": "b"}]}]


# --- /chat with an image -----------------------------------------------------------------


def test_chat_with_image_reads_it_then_answers_the_combined_message(client, images_on, monkeypatch):
    seen = {}

    async def fake_read(data_url, message):
        seen["read"] = (data_url, message)
        return "An error screen: bKash transfer Tk 5,000 failed, code E-402."

    async def fake_classify(message, recent_turns=None):
        seen["classified"] = message
        return KbQuestion()

    monkeypatch.setattr(chat_module, "read_image", fake_read)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "why did this fail?", "image": PNG_URL}, headers=AUTH_HEADERS)

    events = _parse_sse(resp.text)
    assert [name for name, _ in events][0] == "image"
    assert events[0][1] == {"text": "An error screen: bKash transfer Tk 5,000 failed, code E-402."}
    assert [name for name, _ in events][-1] == "done"
    assert seen["read"] == (PNG_URL, "why did this fail?")
    assert seen["classified"] == (
        "why did this fail?\n\n(Attached image: An error screen: bKash transfer Tk 5,000 failed, code E-402.)")


def test_chat_with_image_when_disabled_is_an_error_event(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_IMAGE_INPUT", False)
    resp = client.post("/chat", json={"message": "what is this", "image": PNG_URL}, headers=AUTH_HEADERS)
    assert _parse_sse(resp.text) == [("error", {"detail": "Image input isn't enabled for this assistant.",
                                         "customer_safe": True, "retryable": False})]


def test_chat_with_bad_image_is_an_error_event(client, images_on):
    resp = client.post("/chat", json={"message": "x", "image": "data:image/svg+xml;base64,PHN2Zz4="},
                       headers=AUTH_HEADERS)
    assert _parse_sse(resp.text) == [("error", {"detail": "Attach a PNG, JPEG, WebP or GIF image.",
                                         "customer_safe": True, "retryable": False})]


def test_chat_with_image_model_failure_is_an_error_event(client, images_on, monkeypatch):
    async def boom(data_url, message):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(chat_module, "read_image", boom)
    resp = client.post("/chat", json={"message": "x", "image": PNG_URL}, headers=AUTH_HEADERS)
    assert _parse_sse(resp.text) == [("error", {"detail": "The attached image couldn't be read right now.",
                                         "customer_safe": True, "retryable": True})]


def test_capabilities(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_IMAGE_INPUT", True)
    monkeypatch.setattr(settings, "MAX_IMAGE_MB", 5)
    assert client.get("/chat/capabilities").status_code == 401
    resp = client.get("/chat/capabilities", headers=AUTH_HEADERS)
    body = resp.json()
    assert body["image_input"] is True and body["max_image_mb"] == 5
