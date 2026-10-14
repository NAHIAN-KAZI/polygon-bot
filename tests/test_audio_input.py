"""Voice input: the model transcribes a recorded WAV and the transcript is answered like
typed text. Off unless LLM_AUDIO_INPUT is set."""
import asyncio
import base64
import struct

import httpx
import pytest

import app.banking.routing as routing
import app.routes.chat as chat_module
from app import llm_backend
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, KbQuestion
from app.config import settings
from app.conversation import speech
from tests.conftest import AUTH_HEADERS
from tests.test_chat_integration_contract import _install_kb_fakes, _install_session_fakes, _parse_sse


def _wav(seconds: float, rate: int = 16000) -> bytes:
    data = b"\0\0" * int(seconds * rate)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


def _url(raw: bytes) -> str:
    return "data:audio/wav;base64," + base64.b64encode(raw).decode()


WAV_URL = _url(_wav(2.0))


@pytest.fixture
def audio_on(monkeypatch):
    monkeypatch.setattr(settings, "LLM_AUDIO_INPUT", True)
    monkeypatch.setattr(settings, "MAX_AUDIO_SECONDS", 60)


# --- decode_audio ----------------------------------------------------------------------


def test_decode_accepts_a_wav_and_measures_it():
    assert base64.b64decode(speech.decode_audio(WAV_URL)) == _wav(2.0)


@pytest.mark.parametrize("bad", [
    "data:audio/webm;base64,AAAA",                     # only WAV is accepted
    "https://example.com/voice.wav",                   # URLs are never fetched
    "data:audio/wav;base64,***",
    _url(b"not a wav file at all, just some bytes......"),
])
def test_decode_rejects_other_input(bad):
    with pytest.raises(speech.AudioInputError):
        speech.decode_audio(bad)


def test_decode_rejects_too_long_and_too_short(monkeypatch):
    monkeypatch.setattr(settings, "MAX_AUDIO_SECONDS", 5)
    with pytest.raises(speech.AudioInputError, match="at most 5 seconds"):
        speech.decode_audio(_url(_wav(6)))
    with pytest.raises(speech.AudioInputError, match="too short"):
        speech.decode_audio(_url(_wav(0.1)))


# --- transcribe --------------------------------------------------------------------------


def test_transcribe_refuses_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_AUDIO_INPUT", False)
    with pytest.raises(speech.AudioInputError, match="isn't enabled"):
        asyncio.run(speech.transcribe(WAV_URL))


def test_transcribe_sends_audio_to_model(audio_on, monkeypatch):
    seen = {}

    async def fake_post(path, payload, *, timeout):
        seen["payload"], seen["timeout"] = payload, timeout
        return {"message": {"content": ' "send 500 taka to bkash 01711111111" '}}

    monkeypatch.setattr(speech.llm_backend, "post", fake_post)
    assert asyncio.run(speech.transcribe(WAV_URL)) == "send 500 taka to bkash 01711111111"
    assert seen["payload"]["messages"][0]["audio"] == [WAV_URL.split(",", 1)[1]]
    assert seen["timeout"] is not None


def test_transcribe_silence_is_an_error(audio_on, monkeypatch):
    async def fake_post(path, payload, *, timeout):
        return {"message": {"content": "  "}}

    monkeypatch.setattr(speech.llm_backend, "post", fake_post)
    with pytest.raises(speech.AudioInputError, match="couldn't hear"):
        asyncio.run(speech.transcribe(WAV_URL))


# --- translator: "audio" -> OpenAI input_audio parts -------------------------------------


def test_openai_translation_sends_input_audio_parts(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MODEL", "gemma4")
    body = llm_backend._to_openai("/api/chat", {"messages": [{"role": "user", "content": "hear", "audio": ["UklGRg=="]}]})
    assert body["messages"][0]["content"] == [
        {"type": "text", "text": "hear"},
        {"type": "input_audio", "input_audio": {"data": "UklGRg==", "format": "wav"}},
    ]


# --- /chat with a voice message ---------------------------------------------------------


def _answer_as_kb(monkeypatch, seen):
    async def fake_classify(message, recent_turns=None):
        seen["classified"] = message
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)


def test_voice_message_alone_is_transcribed_then_answered(client, audio_on, monkeypatch):
    seen = {}

    async def fake_transcribe(data_url):
        return "what are your branch hours"

    monkeypatch.setattr(chat_module, "transcribe", fake_transcribe)
    _answer_as_kb(monkeypatch, seen)

    resp = client.post("/chat", json={"audio": WAV_URL}, headers=AUTH_HEADERS)

    events = _parse_sse(resp.text)
    assert events[0] == ("transcript", {"text": "what are your branch hours"})
    assert events[-1][0] == "done"
    assert seen["classified"] == "what are your branch hours"


def test_typed_text_stays_in_front_of_the_transcript(client, audio_on, monkeypatch):
    seen = {}

    async def fake_transcribe(data_url):
        return "and to bkash"

    monkeypatch.setattr(chat_module, "transcribe", fake_transcribe)
    _answer_as_kb(monkeypatch, seen)
    client.post("/chat", json={"message": "send 500", "audio": WAV_URL}, headers=AUTH_HEADERS)
    assert seen["classified"] == "send 500\n\nand to bkash"


def test_voice_message_with_image_handles_both(client, audio_on, monkeypatch):
    seen = {}
    monkeypatch.setattr(settings, "LLM_IMAGE_INPUT", True)

    async def fake_transcribe(data_url):
        return "why did this fail"

    async def fake_read(data_url, message):
        seen["image_message"] = message
        return "A failed transfer."

    monkeypatch.setattr(chat_module, "transcribe", fake_transcribe)
    monkeypatch.setattr(chat_module, "read_image", fake_read)
    _answer_as_kb(monkeypatch, seen)
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 32).decode()

    resp = client.post("/chat", json={"audio": WAV_URL, "image": png}, headers=AUTH_HEADERS)

    assert [name for name, _ in _parse_sse(resp.text)][:2] == ["transcript", "image"]
    assert seen["image_message"] == "why did this fail"
    assert seen["classified"] == "why did this fail\n\n(Attached image: A failed transfer.)"


@pytest.mark.parametrize("mode, shows_transcript", [("both", True), ("audio", False)])
def test_routing_hears_the_recording_and_everything_runs_on_the_transcript(
        client, audio_on, monkeypatch, mode, shows_transcript):
    seen = {}

    async def fake_transcribe(data_url):
        return "আমার ব্যালেন্স কত"

    async def fake_classify(message, recent_turns=None):
        seen["classified"] = message
        seen["heard_audio"] = routing.heard_audio.get()
        return KbQuestion()

    monkeypatch.setattr(chat_module, "transcribe", fake_transcribe)
    _answer_as_kb(monkeypatch, seen)
    monkeypatch.setattr(chat_module, "classify", fake_classify)

    resp = client.post("/chat", json={"audio": WAV_URL, "audio_mode": mode}, headers=AUTH_HEADERS)

    names = [name for name, _ in _parse_sse(resp.text)]
    assert ("transcript" in names) is shows_transcript  # the mobile app ("audio") never shows one
    assert names[-1] == "done"
    assert seen["classified"] == "আমার ব্যালেন্স কত"
    assert seen["heard_audio"] == speech.decode_audio(WAV_URL)
    assert routing.heard_audio.get() is None


def test_audio_mode_banking_reply_answers_what_was_said(client, audio_on, monkeypatch):
    # Live 2026-10-14: an audio-mode balance question was routed to accounts, but the reply
    # writer only got a "(voice message)" placeholder and answered "I cannot process voice
    # messages".
    seen = {}

    async def fake_transcribe(data_url):
        return "how much money is in my account"

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="accounts", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id="cust-123")

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"data": {"accounts": [{"accountNumber": "1234567890"}]}})

    async def fake_synthesize_reply(message, service, subservice, data):
        seen["reply_to"] = message
        return "You have one account."

    monkeypatch.setattr(chat_module, "transcribe", fake_transcribe)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "_synthesize_reply", fake_synthesize_reply)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"audio": WAV_URL, "audio_mode": "audio"},
                       headers={**AUTH_HEADERS, "Authorization": "Bearer sometoken"})

    events = _parse_sse(resp.text)
    assert "transcript" not in [name for name, _ in events]
    assert seen["reply_to"] == "how much money is in my account"
    assert next(data for name, data in events if name == "result")["type"] == "BANKING_SERVICE"

def test_voice_input_disabled_is_an_error_event(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_AUDIO_INPUT", False)
    resp = client.post("/chat", json={"audio": WAV_URL}, headers=AUTH_HEADERS)
    assert _parse_sse(resp.text) == [("error", {"detail": "Voice input isn't enabled for this assistant."})]


def test_voice_model_failure_is_an_error_event(client, audio_on, monkeypatch):
    async def boom(data_url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(chat_module, "transcribe", boom)
    resp = client.post("/chat", json={"audio": WAV_URL}, headers=AUTH_HEADERS)
    assert _parse_sse(resp.text) == [("error", {"detail": "The voice message couldn't be heard right now."})]


def test_message_still_required_without_audio(client):
    assert client.post("/chat", json={}, headers=AUTH_HEADERS).status_code == 422
    assert client.post("/chat", json={"message": "  "}, headers=AUTH_HEADERS).status_code == 422


def test_capabilities_report_audio(client, audio_on):
    body = client.get("/chat/capabilities", headers=AUTH_HEADERS).json()
    assert body["audio_input"] is True and body["max_audio_seconds"] == 60


def test_default_voice_limit_fits_what_gemma_hears():
    # Gemma 4 hears at most 30 s per clip and the server drops the rest without an error.
    from app.config import Settings
    assert Settings().MAX_AUDIO_SECONDS <= 30
