"""Voice input: the model transcribes a recorded voice message, and the transcript is
answered exactly like a typed message -- routing, grounding and confirmations all run on
the text, so speaking can't skip any step. The transcript comes from the model when it
hears audio (LLM_AUDIO_INPUT, gemma4 on vLLM), or from the separate speech-to-text server
(STT_URL, stt_service/) in the "nemo" voice mode."""
import base64
import binascii
import re
import struct

import httpx

from app import llm_backend
from app.config import settings

_DATA_URL_RE = re.compile(r"^data:audio/(?:wav|x-wav|wave);base64,(.+)$", re.S)

# Tuned on spoken Bangla, English and mixed test clips (experiments/dynamic_suite/voice_route.py):
# - without the script rule gemma4 wrote Bangla phonetically in Devanagari ("अमरकार…");
# - without being told speakers mix English words into Bangla, mixed speech became invented
#   English sentences;
# - saying the speaker "talks about banking" made it invent transfers and amounts that were
#   never spoken ("how much is in my account" -> "transfer crores"), so the prompt forbids
#   adding words or numbers instead.
_TRANSCRIBE_PROMPT = (
    "Transcribe this voice message word for word, exactly as spoken. The speaker is from "
    "Bangladesh and speaks Bangla, English, or Bangla with some English words mixed in. Write "
    "Bangla words in Bangla script (বাংলা) and English words in English letters; never use "
    "Devanagari or any other script, and never translate. Write only words you actually hear: "
    "if a word is unclear, write your best guess of how it sounds, and never add words, "
    "amounts or numbers that were not spoken. Write spoken numbers as digits. Reply with only "
    "the transcript. If there is no speech, reply with nothing."
)


class AudioInputError(ValueError):
    """The voice message can't be used; the message is safe to show the customer."""


def _wav_seconds(raw: bytes) -> float:
    """Duration of a PCM WAV file; raises AudioInputError if it isn't one."""
    if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise AudioInputError("Send the voice message as a WAV recording.")
    pos, byte_rate, data_size = 12, None, None
    while pos + 8 <= len(raw):
        chunk_id, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        if chunk_id == b"fmt " and size >= 12:
            byte_rate = struct.unpack("<I", raw[pos + 16:pos + 20])[0]
        elif chunk_id == b"data":
            data_size = min(size, len(raw) - pos - 8)
            break
        pos += 8 + size + (size & 1)
    if not byte_rate or data_size is None:
        raise AudioInputError("The voice message couldn't be read.")
    return data_size / byte_rate


def decode_audio(data_url: str) -> str:
    """The raw base64 of a data:audio/wav URL, after checking format and length."""
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise AudioInputError("Send the voice message as a WAV recording.")
    b64 = match.group(1).strip()
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise AudioInputError("The voice message couldn't be read.")
    seconds = _wav_seconds(raw)
    if seconds > settings.MAX_AUDIO_SECONDS:
        raise AudioInputError(f"Voice messages can be at most {settings.MAX_AUDIO_SECONDS} seconds.")
    if seconds < 0.3:
        raise AudioInputError("The voice message was too short. Please record it again and speak for a moment.")
    return b64


async def transcribe(data_url: str) -> str:
    """What the customer said, as text."""
    if not settings.LLM_AUDIO_INPUT:
        raise AudioInputError("Voice input isn't enabled for this assistant.")
    b64 = decode_audio(data_url)
    data = await llm_backend.post(
        "/api/chat",
        {
            "model": settings.OLLAMA_MODEL,
            "messages": [{"role": "user", "content": _TRANSCRIBE_PROMPT, "audio": [b64]}],
            "stream": False,
            "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0, "num_predict": 300},
        },
        timeout=60.0,
    )
    text = ((data.get("message") or {}).get("content") or "").strip().strip('"').strip()
    if not text:
        raise AudioInputError("I couldn't hear anything in that voice message. Please try again.")
    return text


async def transcribe_nemo(data_url: str) -> str:
    """What the customer said, as text, from the speech-to-text server (STT_URL)."""
    if not settings.STT_URL:
        raise AudioInputError("The Titu speech model isn't enabled for this assistant.")
    raw = base64.b64decode(decode_audio(data_url))
    headers = {"Content-Type": "audio/wav"}
    if settings.STT_API_KEY:
        headers["X-API-Key"] = settings.STT_API_KEY
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{settings.STT_URL}/transcribe", content=raw, headers=headers)
        resp.raise_for_status()
    text = (resp.json().get("text") or "").strip()
    if not text:
        raise AudioInputError("I couldn't hear anything in that voice message. Please try again.")
    return text
