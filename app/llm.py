from typing import AsyncGenerator

from app import llm_backend
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


SYSTEM_PROMPT_NEAREST = (
    f"{GLOBAL_PERSONA}\n\n"
    "Task: the bank knowledge below is related to the customer's question but does not answer it directly. "
    f"If the question isn't about banking: {KIND_PURPOSE['decline_offtopic']} Don't name or discuss the "
    "off-topic subject, and ignore the knowledge below. If it is about banking: say plainly that you don't "
    "have that exact information, mention in one sentence what related information you do have (only what "
    "the knowledge below says, never as the answer), and ask one short question that would help you find "
    "what they need. Never invent an answer.\n" + _KB_SHARED_RULES
)


def _format_chunk(c: dict) -> str:
    page_suffix = f", page {c['page']}" if c.get("page") else ""
    return f"[source: {c['filename']}{page_suffix}]\n{c['text']}"


def _live_block(live: str | None) -> str:
    if not live:
        return ""
    return (
        "The bank's own list of cards right now. It is complete: when the customer asks which cards the bank has "
        "or compares them, name every card in it, spelled as written and split as it is, never replace the cards "
        "by their networks. Use the knowledge for what each card gives, costs and requires.\n"
        f"{live}\n\n"
    )


def _language_line(language: str | None) -> str:
    return f"Write the answer in {language}.\n\n" if language else ""


def build_prompt(question: str, context_chunks: list[dict], nearest: list[dict] | None = None,
                 live: str | None = None, language: str | None = None) -> str:
    if not context_chunks and nearest:
        related = "\n\n".join(_format_chunk(c) for c in nearest)
        return (
            f"{SYSTEM_PROMPT_NEAREST}\n\n"
            f"{_language_line(language)}"
            f"{_live_block(live)}"
            f"Related knowledge:\n{related}\n\n"
            f"Question: {question}\n"
            f"Answer:"
        )
    if not context_chunks and live:
        return (
            f"{SYSTEM_PROMPT_WITH_CONTEXT}\n\n"
            f"{_language_line(language)}"
            f"Context:\n{_live_block(live)}"
            f"Question: {question}\n"
            f"Answer:"
        )
    if not context_chunks:
        return (
            f"{SYSTEM_PROMPT_NO_CONTEXT}\n\n"
            f"{_language_line(language)}"
            f"Question: {question}\n"
            f"Answer:"
        )
    context = "\n\n".join(_format_chunk(c) for c in context_chunks)
    return (
        f"{SYSTEM_PROMPT_WITH_CONTEXT}\n\n"
        f"{_language_line(language)}"
        f"Context:\n{_live_block(live)}{context}\n\n"
        f"Question: {question}\n"
        f"Answer:"
    )


async def stream_generate(prompt: str) -> AsyncGenerator[str, None]:
    async for data in llm_backend.stream(
        "/api/generate",
        {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": True,
            "think": settings.OLLAMA_THINK,
            "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.2},
        },
        timeout=60.0,  # per read: a stalled model server ends the stream instead of hanging it
    ):
        token = data.get("response", "")
        if token:
            yield token
        if data.get("done"):
            break


async def check_ollama() -> bool:
    """Whether the text-generation server (Ollama, or the OpenAI-compatible one) answers."""
    return await llm_backend.healthy()
