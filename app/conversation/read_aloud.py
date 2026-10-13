"""Read aloud: a reply spoken by Microsoft's Edge neural voices (edge-tts). The text goes to
Microsoft's servers, so this only runs when TTS_ENABLED is on and the customer asks for it."""
import re

import edge_tts

from app.config import settings

_BANGLA = re.compile(r"[ঀ-৿]")
# Markdown marks the model may write would otherwise be read out or make the voice stumble.
_MARKUP = re.compile(r"[*_#`>|~]+")


def voice_for(text: str) -> str:
    """Replies follow the customer's language, so any Bangla script means a Bangla reply."""
    return settings.TTS_VOICE_BN if _BANGLA.search(text) else settings.TTS_VOICE_EN


def speakable(text: str) -> str:
    return re.sub(r"\s+", " ", _MARKUP.sub(" ", text)).strip()


async def synthesize(text: str) -> bytes:
    """MP3 audio of `text`; empty if the service sent none."""
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice_for(text)).stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return bytes(audio)
