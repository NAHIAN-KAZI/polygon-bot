"""Read aloud (POST /tts): a reply spoken by edge-tts. The real service is never called --
edge_tts.Communicate is replaced by a fake that records what it was asked to speak."""
import pytest

from app.config import settings
from app.conversation import read_aloud
from tests.conftest import AUTH_HEADERS


@pytest.fixture
def tts_on(monkeypatch):
    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    monkeypatch.setattr(settings, "TTS_VOICE_BN", "bn-voice")
    monkeypatch.setattr(settings, "TTS_VOICE_EN", "en-voice")


def _fake_tts(monkeypatch, chunks=(b"ID3", b"mp3"), error=None):
    calls = []

    class FakeCommunicate:
        def __init__(self, text, voice):
            calls.append((text, voice))

        async def stream(self):
            if error:
                raise error
            yield {"type": "WordBoundary", "offset": 0}
            for data in chunks:
                yield {"type": "audio", "data": data}

    monkeypatch.setattr(read_aloud.edge_tts, "Communicate", FakeCommunicate)
    return calls


def test_returns_the_spoken_reply_as_mp3(client, tts_on, monkeypatch):
    calls = _fake_tts(monkeypatch)
    resp = client.post("/tts", json={"text": "Your balance is 500 taka."}, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"ID3mp3"
    assert calls == [("Your balance is 500 taka.", "en-voice")]


@pytest.mark.parametrize("text, voice", [
    ("আপনার ব্যালেন্স ৫০০ টাকা।", "bn-voice"),
    ("আপনার account এ 500 taka আছে", "bn-voice"),  # mixed reply: still the Bangla voice
    ("Your card is blocked.", "en-voice"),
])
def test_bangla_script_picks_the_bangla_voice(tts_on, text, voice):
    assert read_aloud.voice_for(text) == voice


def test_markdown_marks_are_not_read_out(client, tts_on, monkeypatch):
    calls = _fake_tts(monkeypatch)
    client.post("/tts", json={"text": "**Balance:**\n\n# 500 `taka`"}, headers=AUTH_HEADERS)
    assert calls[0][0] == "Balance: 500 taka"


def test_off_by_default_never_contacts_the_service(client, monkeypatch):
    monkeypatch.setattr(settings, "TTS_ENABLED", False)
    calls = _fake_tts(monkeypatch)
    resp = client.post("/tts", json={"text": "hello"}, headers=AUTH_HEADERS)
    assert resp.status_code == 404
    assert calls == []


def test_needs_the_api_key(client, tts_on, monkeypatch):
    calls = _fake_tts(monkeypatch)
    assert client.post("/tts", json={"text": "hello"}).status_code == 401
    assert calls == []


@pytest.mark.parametrize("text", ["", "x" * 4001])
def test_empty_or_overlong_text_is_refused(client, tts_on, monkeypatch, text):
    calls = _fake_tts(monkeypatch)
    assert client.post("/tts", json={"text": text}, headers=AUTH_HEADERS).status_code == 422
    assert calls == []


def test_only_markup_is_nothing_to_read(client, tts_on, monkeypatch):
    calls = _fake_tts(monkeypatch)
    assert client.post("/tts", json={"text": "** ##"}, headers=AUTH_HEADERS).status_code == 422
    assert calls == []


@pytest.mark.parametrize("kwargs", [{"error": ConnectionError("blocked")}, {"chunks": ()}])
def test_service_failure_or_silence_is_a_502(client, tts_on, monkeypatch, kwargs):
    _fake_tts(monkeypatch, **kwargs)
    resp = client.post("/tts", json={"text": "hello"}, headers=AUTH_HEADERS)
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Read aloud is unavailable right now."


@pytest.mark.parametrize("enabled", [True, False])
def test_capabilities_say_whether_read_aloud_is_offered(client, monkeypatch, enabled):
    monkeypatch.setattr(settings, "TTS_ENABLED", enabled)
    assert client.get("/chat/capabilities", headers=AUTH_HEADERS).json()["read_aloud"] is enabled
