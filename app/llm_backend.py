"""The one place text-generation requests leave the app.

Every caller builds an Ollama-native request (/api/chat or /api/generate) and reads an
Ollama-shaped reply. With LLM_PROVIDER=ollama (the default) the request goes to Ollama
unchanged. With LLM_PROVIDER=openai it is translated for an OpenAI-compatible server
(e.g. vLLM) and the reply translated back, so callers never see the difference:

- /api/generate's prompt becomes one user message; all system messages are merged into one
  (Gemma's chat template takes a single system turn and strict user/assistant alternation).
- format "json" becomes JSON mode; a format schema becomes a json_schema response format.
- tools are emulated with a json_schema response format (one {"name", "arguments"} object per
  tool), since the server may run without a tool-call parser -- or, with LLM_TOOL_MODE
  native_auto / native_required, sent as the server's own tool calls. Either way the reply comes
  back as message.tool_calls exactly as Ollama would give it.
- options.temperature / options.num_predict map to temperature / max_tokens; num_ctx and
  think have no OpenAI equivalent and are dropped.
- a message's "images" (raw base64, Ollama's format) become image_url content parts, and
  its "audio" (raw base64 WAV, this app's extension) becomes input_audio parts.

Embeddings are not covered here: they always go to Ollama (app/embeddings.py).
"""
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import AsyncIterator

import httpx

from app.config import settings


@dataclass
class TurnStats:
    """Model usage across every call made while answering one chat message."""
    calls: int = 0
    peak_prompt_tokens: int = 0  # the largest single prompt: how full the context window got
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_seconds: float = 0.0
    began: float = field(default_factory=time.monotonic)
    # One entry per model call: when it started (ms into the turn), how long it took, which prompt it was (the first
    # words of the fixed instruction, never customer text) and its token counts. Shown with the opt-in stats.
    timeline: list = field(default_factory=list)


# Mutable object, so calls made in tasks spawned from the request (which copy the
# context) still add to the same totals.
_turn_stats: ContextVar[TurnStats | None] = ContextVar("llm_turn_stats", default=None)


def start_turn_stats() -> TurnStats:
    stats = TurnStats()
    _turn_stats.set(stats)
    return stats


def _label(path: str, payload: dict) -> str:
    """Which prompt this is, from its opening words: the instruction text comes first, the customer's words later."""
    if path == "/api/generate":
        return str(payload.get("prompt") or "")[:26]
    messages = payload.get("messages") or []
    first = next((m for m in messages if m.get("role") == "system"), messages[0] if messages else {})
    return str(first.get("content") or "")[:26]


def _record(prompt_tokens: int | None, completion_tokens: int | None, started: float, label: str = "") -> None:
    stats = _turn_stats.get()
    if stats is None:
        return
    stats.timeline.append({"start_ms": round((started - stats.began) * 1000),
                           "ms": round((time.monotonic() - started) * 1000), "prompt": label,
                           "prompt_tokens": prompt_tokens or 0, "completion_tokens": completion_tokens or 0})
    stats.calls += 1
    stats.prompt_tokens += prompt_tokens or 0
    stats.completion_tokens += completion_tokens or 0
    stats.peak_prompt_tokens = max(stats.peak_prompt_tokens, prompt_tokens or 0)
    stats.llm_seconds += time.monotonic() - started


_context_window: int | None = None


async def context_window() -> int:
    """The model's context size in tokens: LLM_CONTEXT_WINDOW if set, else the OpenAI-compatible
    server's max_model_len for LLM_MODEL (asked once), else OLLAMA_NUM_CTX."""
    global _context_window
    if settings.LLM_CONTEXT_WINDOW:
        return settings.LLM_CONTEXT_WINDOW
    if not _use_openai():
        return settings.OLLAMA_NUM_CTX
    if _context_window is None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{settings.LLM_BASE_URL}/models", headers=_headers())
                resp.raise_for_status()
                models = resp.json().get("data") or []
            match = next((m for m in models if m.get("id") == settings.LLM_MODEL), models[0] if models else {})
            _context_window = int(match.get("max_model_len") or 0) or settings.OLLAMA_NUM_CTX
        except (httpx.HTTPError, ValueError, TypeError):
            return settings.OLLAMA_NUM_CTX
    return _context_window


def _use_openai() -> bool:
    return settings.LLM_PROVIDER == "openai"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.LLM_API_KEY}"} if settings.LLM_API_KEY else {}


async def post(path: str, payload: dict, *, timeout: float | None) -> dict:
    """Send a non-streamed Ollama request (`path` is "/api/chat" or "/api/generate") and
    return the Ollama-shaped reply. Raises httpx errors exactly like a direct call would."""
    started = time.monotonic()
    if not _use_openai():
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{settings.OLLAMA_BASE_URL}{path}", json=payload)
            resp.raise_for_status()
            data = resp.json()
        _record(data.get("prompt_eval_count"), data.get("eval_count"), started, _label(path, payload))
        return data
    body = _to_openai(path, {**payload, "stream": False})
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.LLM_BASE_URL}/chat/completions", json=body, headers=_headers()
        )
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usage") or {}
    _record(usage.get("prompt_tokens"), usage.get("completion_tokens"), started, _label(path, payload))
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or ""
    if path == "/api/generate":
        return {"response": content, "done": True}
    reply = {"role": "assistant", "content": content}
    native_calls = _native_tool_calls(message.get("tool_calls"), payload.get("tools") or [])
    if native_calls:
        reply = {"role": "assistant", "content": "", "tool_calls": native_calls}
    elif payload.get("tools"):
        calls = _tool_calls_from_json(content, payload["tools"])
        if calls:
            reply = {"role": "assistant", "content": "", "tool_calls": calls}
    return {"message": reply, "done": True}


async def stream(path: str, payload: dict, *, timeout: float | None) -> AsyncIterator[dict]:
    """Send a streamed Ollama request and yield Ollama-shaped chunks, the last with done=True."""
    started = time.monotonic()
    if not _use_openai():
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{settings.OLLAMA_BASE_URL}{path}", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        if chunk.get("done"):
                            _record(chunk.get("prompt_eval_count"), chunk.get("eval_count"), started, _label(path, payload))
                        yield chunk
        return
    body = _to_openai(path, {**payload, "stream": True})
    body["stream_options"] = {"include_usage": True}
    usage: dict = {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", f"{settings.LLM_BASE_URL}/chat/completions", json=body, headers=_headers()
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                usage = event.get("usage") or usage
                delta = ((event.get("choices") or [{}])[0].get("delta") or {})
                text = delta.get("content") or ""
                if text:
                    yield _chunk(path, text, done=False)
    _record(usage.get("prompt_tokens"), usage.get("completion_tokens"), started, _label(path, payload))
    yield _chunk(path, "", done=True)


async def healthy() -> bool:
    """Whether the text-generation server answers."""
    url = (
        f"{settings.LLM_BASE_URL}/models" if _use_openai() else f"{settings.OLLAMA_BASE_URL}/api/tags"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=_headers() if _use_openai() else {})
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _chunk(path: str, text: str, *, done: bool) -> dict:
    if path == "/api/generate":
        return {"response": text, "done": done}
    return {"message": {"role": "assistant", "content": text}, "done": done}


def _to_openai(path: str, payload: dict) -> dict:
    if path == "/api/generate":
        messages = [{"role": "user", "content": payload.get("prompt") or ""}]
        if payload.get("system"):
            messages.insert(0, {"role": "system", "content": payload["system"]})
    else:
        messages = [_plain_message(m) for m in payload.get("messages") or []]
    tools = payload.get("tools")
    native = bool(tools) and settings.LLM_TOOL_MODE != "emulated"
    if tools and not native:
        # After the caller's instructions, not before: with the tool list first, gemma4
        # answered "what are your branch hours?" with ask_clarification instead of the KB.
        messages.append({"role": "system", "content": _tools_instruction(tools)})
    body: dict = {
        "model": settings.LLM_MODEL,
        "messages": _normalise_roles(messages),
        "stream": bool(payload.get("stream")),
    }
    options = payload.get("options") or {}
    if "temperature" in options:
        body["temperature"] = options["temperature"]
    if "num_predict" in options:
        body["max_tokens"] = options["num_predict"]
    fmt = payload.get("format")
    if native:
        # The server's own tool calling (vLLM --enable-auto-tool-choice): "auto" lets the model
        # call in its trained format, "required" forces a call through structured output.
        body["tools"] = tools
        body["tool_choice"] = "required" if settings.LLM_TOOL_MODE == "native_required" else "auto"
    elif tools:
        body["response_format"] = _json_schema("tool_call", _tools_schema(tools))
    elif fmt == "json":
        body["response_format"] = {"type": "json_object"}
    elif isinstance(fmt, dict):
        body["response_format"] = _json_schema("reply", fmt)
    return body


def _plain_message(message: dict) -> dict:
    """An Ollama message as plain role + text; an earlier tool call becomes the JSON the
    model is asked to write when it calls a tool."""
    content = message.get("content") or ""
    calls = message.get("tool_calls")
    if calls and not content:
        fn = calls[0].get("function") or {}
        content = json.dumps({"name": fn.get("name"), "arguments": fn.get("arguments") or {}})
    role = message.get("role") or "user"
    images = message.get("images") or []
    audio = message.get("audio") or []
    if images or audio:
        # Ollama carries raw base64 images beside the text; OpenAI wants content parts.
        # "audio" (raw base64 WAV) is this app's own extension: Ollama has no audio input.
        content = [{"type": "text", "text": content}] + [
            {"type": "image_url", "image_url": {"url": f"data:{_image_mime(b64)};base64,{b64}"}}
            for b64 in images
        ] + [
            {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}}
            for b64 in audio
        ]
    return {"role": "user" if role == "tool" else role, "content": content}


def _image_mime(b64: str) -> str:
    for prefix, mime in (("/9j/", "image/jpeg"), ("iVBOR", "image/png"), ("UklGR", "image/webp"), ("R0lGOD", "image/gif")):
        if b64.startswith(prefix):
            return mime
    return "image/png"


def _merge_content(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a + "\n\n" + b
    parts = lambda c: c if isinstance(c, list) else [{"type": "text", "text": c}]
    return parts(a) + parts(b)


def _normalise_roles(messages: list[dict]) -> list[dict]:
    """All system text first as one message, then user/assistant turns with same-role
    neighbours merged, starting with a user turn."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system" and m["content"])
    turns: list[dict] = []
    for m in messages:
        if m["role"] == "system":
            continue
        if turns and turns[-1]["role"] == m["role"]:
            turns[-1]["content"] = _merge_content(turns[-1]["content"], m["content"])
        else:
            turns.append(dict(m))
    if turns and turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": "(conversation start)"})
    return ([{"role": "system", "content": system}] if system else []) + turns


def _tools_instruction(tools: list[dict]) -> str:
    lines = []
    for tool in tools:
        fn = tool.get("function") or {}
        lines.append(
            f"- {fn.get('name')}: {fn.get('description', '')}\n"
            f"  arguments schema: {json.dumps(fn.get('parameters') or {}, ensure_ascii=False)}"
        )
    return (
        "You have these tools:\n" + "\n".join(lines) + "\n\n"
        "Call exactly one tool by replying only with JSON: "
        '{"name": "<tool name>", "arguments": {<arguments>}}'
    )


def _tools_schema(tools: list[dict]) -> dict:
    return {"anyOf": [
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": [fn.get("name")]},
                "arguments": fn.get("parameters") or {"type": "object"},
            },
            "required": ["name", "arguments"],
        }
        for fn in (tool.get("function") or {} for tool in tools)
    ]}


def _json_schema(name: str, schema: dict) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}


def _native_tool_calls(calls, tools: list[dict]) -> list[dict]:
    """OpenAI tool_calls (arguments as a JSON string) in Ollama's shape (arguments as a dict),
    keeping only calls to the offered tools."""
    names = {(tool.get("function") or {}).get("name") for tool in tools}
    out = []
    for call in calls or []:
        fn = call.get("function") or {}
        if fn.get("name") not in names:
            continue
        try:
            arguments = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            arguments = {}
        out.append({"function": {"name": fn["name"], "arguments": arguments if isinstance(arguments, dict) else {}}})
    return out


def _tool_calls_from_json(content: str, tools: list[dict]) -> list[dict]:
    names = {(tool.get("function") or {}).get("name") for tool in tools}
    try:
        call = json.loads(content)
    except ValueError:
        return []
    if not isinstance(call, dict) or call.get("name") not in names:
        return []
    arguments = call.get("arguments")
    return [{"function": {"name": call["name"], "arguments": arguments if isinstance(arguments, dict) else {}}}]
