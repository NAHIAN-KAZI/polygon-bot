"""POST /tts: a reply as spoken MP3, for the portal's "Read aloud" button. 404 unless
TTS_ENABLED (see app/conversation/read_aloud.py for why it's off by default)."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.config import settings
from app.conversation.read_aloud import speakable, synthesize

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"], dependencies=[Depends(require_api_key)])


class TtsRequest(BaseModel):
    # Long enough for any reply; a cap keeps one click from becoming minutes of audio.
    text: str = Field(min_length=1, max_length=4000)


@router.post("", response_class=Response)
async def read_aloud(req: TtsRequest):
    if not settings.TTS_ENABLED:
        raise HTTPException(status_code=404, detail="Read aloud is not enabled")
    text = speakable(req.text)
    if not text:
        raise HTTPException(status_code=422, detail="Nothing to read aloud")
    try:
        audio = await synthesize(text)
    except Exception:  # an unofficial web service: any failure just means no audio
        logger.warning("read aloud failed", exc_info=True)
        audio = b""
    if not audio:
        raise HTTPException(status_code=502, detail="Read aloud is unavailable right now.")
    return Response(content=audio, media_type="audio/mpeg")
