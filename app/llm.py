import json
from typing import AsyncGenerator

import httpx

from app.config import settings
from app.conversation.persona import GLOBAL_PERSONA, KIND_PURPOSE

# Knowledge-base answers speak in the same global voice as every other message (T-77);
# only the task differs. No sample sentences: the persona decides the wording.
_KB_SHARED_RULES = (
    "Each knowledge section is labeled with an internal reference tag ([source: ...]); "
    "that label is for you only — never repeat or mention it, and never include bracketed "
    "tags, filenames or page numbers. STRICT RULE — NEVER REVEAL THE RETRIEVAL MECHANISM: "
    "never use the words 'context', 'document', 'documents', 'provided', 'retrieval', or "
    "any other phrase that reveals this is a document-lookup system; when you don't know "
    "something, say so the way a person at the bank would. If the message contains vulgar "
    "or offensive language, don't repeat or engage with it; kindly offer help with their "
    "banking instead — this always takes priority."
)

SYSTEM_PROMPT_WITH_CONTEXT = (
    f"{GLOBAL_PERSONA}\n\n"
    "Task: answer the customer's question using ONLY the bank knowledge below. If it "
    "doesn't contain the answer, say honestly that you don't know that. Explain in plain, "
    "everyday words.\n" + _KB_SHARED_RULES
)

SYSTEM_PROMPT_NO_CONTEXT = (
    f"{GLOBAL_PERSONA}\n\n"
    "Task: the bank has no information on this question. "
    f"If it isn't about banking: {KIND_PURPOSE['decline_offtopic']} Don't name or discuss "
    "the off-topic subject. If it is about banking, say honestly that you don't have that "
    "information right now and offer help with something else. Never invent an answer, a "
    "citation or a filename.\n" + _KB_SHARED_RULES
)


def _format_chunk(c: dict) -> str:
    page_suffix = f", page {c['page']}" if c.get("page") else ""
    return f"[source: {c['filename']}{page_suffix}]\n{c['text']}"


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
                "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.2},
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
