import json
from typing import AsyncGenerator

import httpx

from app.config import settings

SYSTEM_PROMPT_WITH_CONTEXT = (
    "You are a helpful assistant. Answer the user's question using ONLY the "
    "context below. If the context doesn't contain the answer, say you don't know. "
    "Cite sources inline using each source's actual bracketed tag shown in the context "
    "(e.g. if you see a section tagged [handbook.md], cite it as [handbook.md]) when you use them."
)

SYSTEM_PROMPT_NO_CONTEXT = (
    "You are a helpful assistant. No relevant documents were found for this question. "
    "Say you don't know, based on the available documents. Do not invent a citation or "
    "reference any filename — none was retrieved."
)


def _format_chunk(c: dict) -> str:
    page_suffix = f" p.{c['page']}" if c.get("page") else ""
    return f"[{c['filename']}{page_suffix}]\n{c['text']}"


def build_prompt(question: str, context_chunks: list[dict]) -> str:
    if not context_chunks:
        return (
            f"{SYSTEM_PROMPT_NO_CONTEXT}\n\n"
            f"Question: {question}\n"
            f"Answer:"
        )
    context = "\n\n".join(_format_chunk(c) for c in context_chunks)
    return (
        f"{SYSTEM_PROMPT_WITH_CONTEXT}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n"
        f"Answer:"
    )


async def stream_generate(prompt: str) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": True,
                "think": settings.OLLAMA_THINK,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("response", "")
                if token:
                    yield token
                if data.get("done"):
                    break


async def check_ollama() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
