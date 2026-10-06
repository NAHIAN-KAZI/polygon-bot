"""compose(): writes EVERY customer-facing message (T-77).

The code decides what happened and hands over structured facts; the global persona
(app/conversation/persona.py) decides the wording for this customer and this moment of
the conversation. Safety lives in validation, not in fixed sentences:
  - every exact value in `must_include` appears verbatim, still attached to its label
    (a card ending never becomes "phone number 0293");
  - every 3+-digit number in the reply is supported by the facts;
  - no currency other than Tk; sane length.
A failed check is retried once at temperature 0 with the reason named. Only if that
also fails does a plain listing of the facts go out; only if the model can't be reached
at all does the one fixed LLM_DOWN_MESSAGE go out.
"""
import json
import logging
import re
from typing import Mapping, Sequence

import httpx

from app.config import settings
from app.conversation.persona import GLOBAL_PERSONA, KIND_EXAMPLE, KIND_PURPOSE, LLM_DOWN_MESSAGE

logger = logging.getLogger("chat.composer")

NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
LONG_DIGITS_RE = re.compile(r"\d{8,}")
_UNMASKED_RE = re.compile(r"\d{6,}")           # a bare 6+ digit run is an unmasked account/card number
_FOREIGN_CURRENCY = ("$", "€", "£", "₹", "USD", "EUR")
_MARKDOWN_RE = re.compile(r"\*\*|^\s*[-*#] ", re.MULTILINE)
_MAX_LEN = 900


def mask_digit_run(match: re.Match) -> str:
    digits = match.group()
    return "•" * (len(digits) - 4) + digits[-4:]


def _plain_number(text: str) -> str:
    """A number without separators or a trailing ".00" ("5,000.00" == "5000")."""
    plain = text.replace(",", "").rstrip(".")
    return plain[:-3] if plain.endswith(".00") else plain


_AMOUNT_VALUE_RE = re.compile(r"^\s*(?:tk\.?|bdt)?\s*\d[\d,]*(?:\.\d+)?\s*$", re.IGNORECASE)


def unsupported_numbers(reply: str, source: str) -> list[str]:
    """Numbers (3+ digits) in a model-written reply that don't appear in the data it
    was given -- a wrong amount must never reach a customer."""
    haystack = source.replace(",", "")
    known = {_plain_number(n) for n in NUMBER_RE.findall(source)}
    return [
        n for n in NUMBER_RE.findall(reply)
        if len(re.sub(r"\D", "", n)) >= 3
        and n.replace(",", "") not in haystack and _plain_number(n) not in known
    ]


def _label_kept(label: str, value: str, text: str) -> bool:
    """`value` appears within a few words after the label's first word ("card ending
    0293", "card ••0293"): the value is still attached to what it describes."""
    head = re.findall(r"\w+", label.lower())
    if not head:
        return value in text
    pattern = re.escape(head[0]) + r"\w*\W+(?:\S+\W+){0,5}?" + re.escape(value)
    return bool(re.search(pattern, text, re.IGNORECASE))


def _find_value(value: str, text: str) -> str | None:
    """How `value` appears in `text`: verbatim, or -- for amounts -- the same number
    written with/without thousands separators, "Tk" spacing or ".00"."""
    if value in text:
        return value
    if not _AMOUNT_VALUE_RE.match(value):
        return None  # only a plain amount may be re-formatted; addresses, names, ids are verbatim
    target = _plain_number(re.sub(r"[^\d.,]", "", value))
    for candidate in NUMBER_RE.findall(text):
        if _plain_number(candidate) == target:
            return candidate
    return None


def check_reply(text: str, facts_json: str, must_include: Mapping[str, str]) -> str | None:
    """None when `text` is safe to send; otherwise the reason (fed back on retry)."""
    if not text:
        return "the reply was empty"
    if len(text) > _MAX_LEN:
        return "the reply was too long"
    if any(symbol in text for symbol in _FOREIGN_CURRENCY):
        return "it used a currency other than Tk"
    if _MARKDOWN_RE.search(text):
        return "it used markdown formatting; write plain text"
    for label, value in must_include.items():
        value = str(value)
        found = _find_value(value, text)
        if found is None:
            return f'it did not include the exact value "{value}" ({label})'
        if label and not _label_kept(label, found, text):
            return f'"{value}" must stay attached to "{label}"'
    support = facts_json + " " + " ".join(map(str, must_include.values()))
    unmasked = [run for run in _UNMASKED_RE.findall(text) if run not in support.replace(",", "")]
    if unmasked:
        return "it contained a long number that is not in the facts"
    bad = unsupported_numbers(text, support)
    if bad:
        return f"it contained numbers that are not in the facts: {', '.join(bad)}"
    return None


def facts_listing(facts: Mapping) -> str:
    """Degraded mode only: the facts as plain 'label: value' lines, no prose."""
    lines = []
    for key, value in facts.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = "; ".join(map(str, value))
        lines.append(f"{key}: {value}")
    return "\n".join(lines) or LLM_DOWN_MESSAGE


def _history_block(history: Sequence[tuple[str, str]] | None) -> str:
    if not history:
        return ""
    lines = [f"{who}: {LONG_DIGITS_RE.sub(mask_digit_run, said)[:300]}" for who, said in history[-6:]]
    return ("Earlier in this chat (context only; answer the customer's latest message below, "
            "not these):\n" + "\n".join(lines) + "\n\n")


# Kinds where every fact matters (safety, consent, irreversible steps): the model is
# told to mention each one; for answers it picks what answers the question.
_MENTION_ALL = {"confirm", "verify", "caution", "summary", "done", "refused_by_bank", "choose", "ask"}


def build_messages(kind: str, facts: Mapping, message: str,
                   history: Sequence[tuple[str, str]] | None,
                   must_include: Mapping[str, str], retry_reason: str | None = None) -> list[dict]:
    """Chat messages for one reply: the persona as the system message; the user message
    holds one worked example of this kind, then the real conversation, the facts, and
    -- last, just before the model answers -- what this message must do."""
    purpose = KIND_PURPOSE.get(kind, KIND_PURPOSE["answer"])
    example = KIND_EXAMPLE.get(kind, KIND_EXAMPLE["answer"])
    checklist = []
    for label, value in must_include.items():
        checklist.append(f"- {label}: {value}  (write \"{value}\" exactly)")
    if kind in _MENTION_ALL:
        for key, value in facts.items():
            if value in (None, "", [], {}) or key in must_include:
                continue
            shown = "; ".join(map(str, value)) if isinstance(value, (list, tuple)) else value
            checklist.append(f"- {key}: {shown}")
    retry = f"Your previous reply was rejected because {retry_reason}. Fix that.\n" if retry_reason else ""
    user = (
        f"Here is an example of this kind of message (different facts):\n{example}\n\n"
        "Now the real one.\n"
        f"{_history_block(history)}"
        f"Customer: {LONG_DIGITS_RE.sub(mask_digit_run, message or '')}\n"
        f"Facts (JSON): {json.dumps(facts, ensure_ascii=False, default=str)}\n\n"
        f"{retry}"
        f"Your task: {purpose}\n"
        + ("Include, in your own words but with exact values:\n" + "\n".join(checklist) + "\n" if checklist else "")
        + "Reply:"
    )
    return [{"role": "system", "content": GLOBAL_PERSONA}, {"role": "user", "content": user}]


# Short replies leave no room for padding and generate fast (~22 tokens/s on the M40).
_MAX_TOKENS = 400  # user decision 2026-10-05: replies capped at 400 tokens


async def generate_chat(messages: list[dict], temperature: float) -> str | None:
    """The model's text for chat `messages`, or None when the model can't be reached."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": temperature,
                                "num_predict": _MAX_TOKENS},
                },
            )
            resp.raise_for_status()
            return ((resp.json().get("message") or {}).get("content") or "").strip().strip('"').strip()
    except Exception as exc:  # unreachable / timeout / bad body
        logger.warning("composer: model call failed: %s", exc)
        return None


async def compose(
    kind: str,
    facts: Mapping,
    *,
    message: str = "",
    history: Sequence[tuple[str, str]] | None = None,
    must_include: Mapping[str, str] | None = None,
) -> str:
    """The customer-facing message for this turn. `facts` is structured data (never
    prose to copy); `must_include` maps a label to an exact value that must appear
    attached to it; `history` is [(speaker, text), ...] of the recent turns."""
    must_include = {k: str(v) for k, v in (must_include or {}).items() if v not in (None, "")}
    facts_json = json.dumps(facts, ensure_ascii=False, default=str)
    reason = None
    for temperature in (0.1, 0.0):
        text = await generate_chat(
            build_messages(kind, facts, message, history, must_include, reason), temperature)
        if text is None:
            return LLM_DOWN_MESSAGE
        reason = check_reply(text, facts_json, must_include)
        if reason is None:
            return text
        logger.info("composer: %s reply rejected: %s", kind, reason)
    return facts_listing({**facts, **must_include})


_SENTENCE_END_RE = re.compile(r"[.!?\n](?=\s)")


async def compose_stream(
    kind: str,
    facts: Mapping,
    *,
    message: str = "",
    history: Sequence[tuple[str, str]] | None = None,
    must_include: Mapping[str, str] | None = None,
):
    """compose(), streamed: yields whole sentences as the model writes them, so the
    customer sees the first words in ~1-2 s. Each released sentence has passed the
    number check; at the end, any exact value the reply left out is added as a short
    "label: value" line (data, not prose) instead of regenerating. A bad number or "$"
    stops the stream: the rest comes from the non-streamed compose()."""
    must_include = {k: str(v) for k, v in (must_include or {}).items() if v not in (None, "")}
    facts_json = json.dumps(facts, ensure_ascii=False, default=str)
    support = facts_json + " " + " ".join(must_include.values())
    messages = build_messages(kind, facts, message, history, must_include)
    full, sent = "", 0
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL, "messages": messages, "stream": True,
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.1,
                                "num_predict": _MAX_TOKENS},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    full += (chunk.get("message") or {}).get("content") or ""
                    done = bool(chunk.get("done"))
                    ends = [m.end() for m in _SENTENCE_END_RE.finditer(full)]
                    cut = len(full) if done else (ends[-1] if ends else 0)
                    safe = full[:cut]
                    if any(sym in safe for sym in _FOREIGN_CURRENCY) or unsupported_numbers(safe, support):
                        raise ValueError("unsupported number in streamed reply")
                    piece = safe[sent:]
                    if sent == 0:
                        piece = piece.lstrip().lstrip('"')
                    if piece:
                        yield piece
                        sent = cut
                    if done:
                        break
    except Exception as exc:
        logger.info("composer: %s stream stopped: %s", kind, exc)
        if sent == 0:
            yield await compose(kind, facts, message=message, history=history, must_include=must_include)
            return
    text = full[:sent]
    missing = {label: value for label, value in must_include.items() if _find_value(value, text) is None}
    if sent == 0:
        yield await compose(kind, facts, message=message, history=history, must_include=must_include)
    elif missing:
        yield "\n" + "\n".join(f"{label.capitalize()}: {value}" for label, value in missing.items())
