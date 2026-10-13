"""Voice "direct audio" mode: while routing, the model hears the recording next to the
transcript. Off by default (transcript only); the transcript still drives every check."""
import app.banking.routing as routing
from app.routes.chat import ChatRequest


def test_transcript_mode_is_text_only():
    assert routing.heard_audio.get() is None
    assert routing._user_turn("freeze my card") == {"role": "user", "content": "freeze my card"}


def test_direct_mode_attaches_the_audio_and_keeps_the_text():
    token = routing.heard_audio.set(("UklGRg==", True))
    try:
        turn = routing._user_turn("freeze my card")
    finally:
        routing.heard_audio.reset(token)
    assert turn["audio"] == ["UklGRg=="]
    assert turn["content"].startswith("freeze my card")
    assert "transcript" in turn["content"]


def test_request_defaults_to_transcript_and_rejects_unknown_modes():
    assert ChatRequest(message="hi").audio_mode == "transcript"
    assert ChatRequest(audio="data:audio/wav;base64,AAAA", audio_mode="both").audio_mode == "both"
    assert ChatRequest(audio="data:audio/wav;base64,AAAA", audio_mode="audio").audio_mode == "audio"
    try:
        ChatRequest(message="hi", audio_mode="other")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown audio_mode accepted")


def test_audio_only_marks_the_text_as_a_placeholder():
    token = routing.heard_audio.set(("UklGRg==", False))
    try:
        turn = routing._user_turn("(voice message)")
    finally:
        routing.heard_audio.reset(token)
    assert turn["audio"] == ["UklGRg=="]
    assert "placeholder" in turn["content"]
