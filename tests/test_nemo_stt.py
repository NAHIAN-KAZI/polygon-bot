"""Voice "nemo" mode: the transcript comes from the separate speech-to-text server
(STT_URL, stt_service/) instead of the model, then is answered like typed text."""
import asyncio
import base64

import httpx
import pytest

import app.banking.routing as routing
import app.routes.chat as chat_module
from app.config import settings
from app.conversation import speech
from app.routes.chat import ChatRequest
from tests.conftest import AUTH_HEADERS
from tests.test_audio_input import WAV_URL, _answer_as_kb, _wav
from tests.test_chat_integration_contract import _parse_sse


@pytest.fixture
def stt_on(monkeypatch):
    monkeypatch.setattr(settings, "STT_URL", "http://stt.test:8001")
    monkeypatch.setattr(settings, "STT_API_KEY", "k3y")
    monkeypatch.setattr(settings, "MAX_AUDIO_SECONDS", 60)


def _fake_server(monkeypatch, respond):
    """Route speech.py's httpx calls to `respond(request) -> httpx.Response`."""
    seen = []
    real = httpx.AsyncClient

    def handler(request):
        seen.append(request)
        return respond(request)

    monkeypatch.setattr(speech.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


# --- transcribe_nemo ---------------------------------------------------------------------


def test_refuses_when_no_server_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "STT_URL", "")
    with pytest.raises(speech.AudioInputError, match="isn't enabled"):
        asyncio.run(speech.transcribe_nemo(WAV_URL))


def test_sends_the_wav_with_the_key_and_returns_the_text(stt_on, monkeypatch):
    seen = _fake_server(monkeypatch, lambda r: httpx.Response(200, json={"text": "  আমার ব্যালেন্স কত  "}))
    assert asyncio.run(speech.transcribe_nemo(WAV_URL)) == "আমার ব্যালেন্স কত"
    req = seen[0]
    assert str(req.url) == "http://stt.test:8001/transcribe"
    assert req.content == _wav(2.0)
    assert req.headers["content-type"] == "audio/wav"
    assert req.headers["x-api-key"] == "k3y"


def test_no_key_header_without_a_key(stt_on, monkeypatch):
    monkeypatch.setattr(settings, "STT_API_KEY", "")
    seen = _fake_server(monkeypatch, lambda r: httpx.Response(200, json={"text": "hi"}))
    asyncio.run(speech.transcribe_nemo(WAV_URL))
    assert "x-api-key" not in seen[0].headers


def test_bad_audio_never_reaches_the_server(stt_on, monkeypatch):
    seen = _fake_server(monkeypatch, lambda r: httpx.Response(200, json={"text": "hi"}))
    with pytest.raises(speech.AudioInputError):
        asyncio.run(speech.transcribe_nemo("data:audio/webm;base64,AAAA"))
    assert seen == []


def test_silence_is_an_error(stt_on, monkeypatch):
    _fake_server(monkeypatch, lambda r: httpx.Response(200, json={"text": " "}))
    with pytest.raises(speech.AudioInputError, match="couldn't hear"):
        asyncio.run(speech.transcribe_nemo(WAV_URL))


def test_server_error_raises(stt_on, monkeypatch):
    _fake_server(monkeypatch, lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(speech.transcribe_nemo(WAV_URL))


# --- /chat in nemo mode ------------------------------------------------------------------


def test_request_accepts_nemo_mode():
    assert ChatRequest(audio=WAV_URL, audio_mode="nemo").audio_mode == "nemo"


def test_nemo_transcript_is_answered_as_text_without_the_model_hearing(client, stt_on, monkeypatch):
    monkeypatch.setattr(settings, "LLM_AUDIO_INPUT", False)  # works without an audio model
    seen = {}

    async def fake_nemo(data_url):
        seen["nemo"] = data_url
        return "আমার ব্যালেন্স কত"

    async def not_called(data_url):
        raise AssertionError("model transcription used in nemo mode")

    async def fake_classify(message, recent_turns=None):
        seen["heard_audio"] = routing.heard_audio.get()
        return routing.KbQuestion()

    monkeypatch.setattr(chat_module, "transcribe_nemo", fake_nemo)
    monkeypatch.setattr(chat_module, "transcribe", not_called)
    _answer_as_kb(monkeypatch, seen)
    monkeypatch.setattr(chat_module, "classify", fake_classify)

    resp = client.post("/chat", json={"audio": WAV_URL, "audio_mode": "nemo"}, headers=AUTH_HEADERS)

    events = _parse_sse(resp.text)
    assert events[0] == ("transcript", {"text": "আমার ব্যালেন্স কত"})
    assert events[-1][0] == "done"
    assert seen["nemo"] == WAV_URL
    assert seen["heard_audio"] is None


def test_nemo_server_down_is_an_error_event(client, stt_on, monkeypatch):
    async def boom(data_url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(chat_module, "transcribe_nemo", boom)
    resp = client.post("/chat", json={"audio": WAV_URL, "audio_mode": "nemo"}, headers=AUTH_HEADERS)
    assert _parse_sse(resp.text) == [("error", {"detail": "The voice message couldn't be heard right now."})]


@pytest.mark.parametrize("audio_model, stt_url, modes", [
    (True, "", ["both", "transcript", "audio"]),
    (True, "http://stt.test:8001", ["both", "transcript", "audio", "nemo"]),
    (False, "http://stt.test:8001", ["nemo"]),
    (False, "", []),
])
def test_capabilities_list_the_offered_voice_modes(client, monkeypatch, audio_model, stt_url, modes):
    monkeypatch.setattr(settings, "LLM_AUDIO_INPUT", audio_model)
    monkeypatch.setattr(settings, "STT_URL", stt_url)
    body = client.get("/chat/capabilities", headers=AUTH_HEADERS).json()
    assert body["voice_modes"] == modes
    assert body["audio_input"] is bool(modes)
