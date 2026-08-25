import json

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key
from app.config import settings
from app.embeddings import embed_text
from app.llm import build_prompt, stream_generate
from app.vectorstore import search

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=settings.MAX_TOP_K)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _chat_stream(req: ChatRequest):
    top_k = req.top_k or settings.DEFAULT_TOP_K
    try:
        query_vector = await embed_text(req.message)
        hits = search(query_vector, top_k)
    except httpx.HTTPStatusError as e:
        yield _sse("error", {"detail": f"Embedding model rejected the request: {e.response.text.strip()}"})
        return
    except httpx.HTTPError:
        yield _sse("error", {"detail": "Embedding model (Ollama) is unreachable"})
        return
    except Exception:
        yield _sse("error", {"detail": "Vector store (Qdrant) is unreachable"})
        return

    prompt = build_prompt(req.message, hits)
    try:
        async for token in stream_generate(prompt):
            yield _sse("token", {"token": token})
    except httpx.HTTPError:
        yield _sse("error", {"detail": "Generation model (Ollama) failed or became unreachable mid-stream"})
        return

    yield _sse("done", {})


@router.post("")
async def chat(req: ChatRequest):
    return StreamingResponse(_chat_stream(req), media_type="text/event-stream")
