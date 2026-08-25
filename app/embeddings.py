import asyncio

import httpx

from app.config import settings

_EMBED_CONCURRENCY = asyncio.Semaphore(4)
_TOO_LARGE_MARKERS = ("too large to process", "exceeds the context length", "context length")
_MIN_SPLIT_CHARS = 40


async def _embed_once(text: str, client: httpx.AsyncClient) -> list[float]:
    resp = await client.post(
        f"{settings.OLLAMA_BASE_URL}/api/embeddings",
        json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _is_too_large_error(e: httpx.HTTPStatusError) -> bool:
    body = e.response.text.lower()
    return any(marker in body for marker in _TOO_LARGE_MARKERS)


async def embed_text(text: str, client: httpx.AsyncClient | None = None) -> list[float]:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=60.0)
    try:
        return await _embed_with_fallback(text, client)
    finally:
        if owns_client:
            await client.aclose()


async def _embed_with_fallback(text: str, client: httpx.AsyncClient) -> list[float]:
    """Embed text; if Ollama rejects it as too long for the embedding model's
    context window, bisect on a whitespace boundary and average the two
    halves' embeddings (cheap, avoids losing the chunk entirely)."""
    try:
        return await _embed_once(text, client)
    except httpx.HTTPStatusError as e:
        if not _is_too_large_error(e) or len(text) <= _MIN_SPLIT_CHARS:
            raise
        mid = len(text) // 2
        split_at = text.rfind(" ", 0, mid)
        split_at = split_at if split_at > 0 else mid
        left, right = text[:split_at], text[split_at:]
        left_vec, right_vec = await asyncio.gather(
            _embed_with_fallback(left, client), _embed_with_fallback(right, client)
        )
        return [(a + b) / 2 for a, b in zip(left_vec, right_vec)]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60.0) as client:

        async def _one(t: str) -> list[float]:
            async with _EMBED_CONCURRENCY:
                return await _embed_with_fallback(t, client)

        return await asyncio.gather(*(_one(t) for t in texts))
