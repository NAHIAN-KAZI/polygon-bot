"""app/llm_backend.py: Ollama requests pass through unchanged by default; with
LLM_PROVIDER=openai they are translated for an OpenAI-compatible server and the reply
translated back to Ollama's shape. The server is never reached: httpx is patched."""
import asyncio
import json

import httpx
import pytest

from app import llm_backend
from app.banking.routing import build_tools
from app.config import settings


class _Resp:
    def __init__(self, body, status=200):
        self._body = body
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://llm/x")
            raise httpx.HTTPStatusError("bad", request=request, response=httpx.Response(self.status_code, request=request))

    def json(self):
        return self._body


class _Stream:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _completion(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@pytest.fixture
def openai(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://llm:8000/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemma4")
    monkeypatch.setattr(settings, "LLM_API_KEY", "")


def _capture_post(monkeypatch, body):
    seen = {}

    async def fake_post(self, url, *args, **kwargs):
        seen["url"], seen["json"], seen["headers"] = url, kwargs.get("json"), kwargs.get("headers")
        return _Resp(body)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return seen


def _run(coro):
    return asyncio.run(coro)


# --- default provider: unchanged Ollama traffic ----------------------------------


def test_ollama_provider_posts_payload_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    payload = {"model": "llama3.1:8b", "prompt": "hi", "stream": False, "format": "json"}
    seen = _capture_post(monkeypatch, {"response": "{}", "done": True})
    assert _run(llm_backend.post("/api/generate", payload, timeout=5)) == {"response": "{}", "done": True}
    assert seen["url"] == f"{settings.OLLAMA_BASE_URL}/api/generate"
    assert seen["json"] == payload


def test_ollama_provider_stream_parses_ndjson(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    lines = [json.dumps({"message": {"content": "Hi"}, "done": False}), "",
             json.dumps({"message": {"content": ""}, "done": True})]
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda self, *a, **k: _Stream(lines))

    async def go():
        return [c async for c in llm_backend.stream("/api/chat", {"messages": []}, timeout=5)]

    assert _run(go()) == [{"message": {"content": "Hi"}, "done": False},
                          {"message": {"content": ""}, "done": True}]


# --- openai provider: request translation ----------------------------------------


def test_generate_becomes_one_user_message_with_json_mode(openai, monkeypatch):
    seen = _capture_post(monkeypatch, _completion('{"answer": "confirm"}'))
    reply = _run(llm_backend.post("/api/generate", {
        "model": "llama3.1:8b", "prompt": "Classify", "stream": False, "format": "json", "think": False,
        "options": {"num_ctx": 8192, "temperature": 0},
    }, timeout=5))
    assert reply == {"response": '{"answer": "confirm"}', "done": True}
    assert seen["url"] == "http://llm:8000/v1/chat/completions"
    assert seen["json"] == {
        "model": "gemma4",
        "messages": [{"role": "user", "content": "Classify"}],
        "stream": False,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }


def test_chat_merges_system_messages_and_maps_options(openai, monkeypatch):
    seen = _capture_post(monkeypatch, _completion("Hello"))
    reply = _run(llm_backend.post("/api/chat", {
        "messages": [
            {"role": "system", "content": "A"},
            {"role": "user", "content": "q1"},
            {"role": "system", "content": "B"},
            {"role": "user", "content": "q2"},
        ],
        "options": {"temperature": 0.3, "num_predict": 400},
    }, timeout=5))
    assert reply == {"message": {"role": "assistant", "content": "Hello"}, "done": True}
    assert seen["json"]["messages"] == [
        {"role": "system", "content": "A\n\nB"},
        {"role": "user", "content": "q1\n\nq2"},
    ]
    assert seen["json"]["temperature"] == 0.3
    assert seen["json"]["max_tokens"] == 400
    assert "response_format" not in seen["json"]


def test_format_schema_becomes_json_schema(openai, monkeypatch):
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    seen = _capture_post(monkeypatch, _completion('{"a": 1}'))
    _run(llm_backend.post("/api/generate", {"prompt": "x", "format": schema}, timeout=5))
    assert seen["json"]["response_format"] == {
        "type": "json_schema", "json_schema": {"name": "reply", "schema": schema}}


def test_api_key_sent_as_bearer(openai, monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "secret")
    seen = _capture_post(monkeypatch, _completion("ok"))
    _run(llm_backend.post("/api/generate", {"prompt": "x"}, timeout=5))
    assert seen["headers"] == {"Authorization": "Bearer secret"}


def test_conversation_never_starts_with_assistant(openai, monkeypatch):
    seen = _capture_post(monkeypatch, _completion("ok"))
    _run(llm_backend.post("/api/chat", {"messages": [
        {"role": "system", "content": "S"}, {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "q"}]}, timeout=5))
    assert [m["role"] for m in seen["json"]["messages"]] == ["system", "user", "assistant", "user"]


# --- openai provider: tool emulation ---------------------------------------------


def test_tools_are_emulated_with_a_json_schema_and_returned_as_tool_calls(openai, monkeypatch):
    tools = build_tools()
    call = {"name": "ask_clarification", "arguments": {"question": "Which card?"}}
    seen = _capture_post(monkeypatch, _completion(json.dumps(call)))
    reply = _run(llm_backend.post("/api/chat", {
        "messages": [{"role": "system", "content": "Route."}, {"role": "user", "content": "card"}],
        "tools": tools,
    }, timeout=5))
    assert reply["message"]["tool_calls"] == [
        {"function": {"name": "ask_clarification", "arguments": {"question": "Which card?"}}}]
    assert reply["message"]["content"] == ""
    body = seen["json"]
    assert "tools" not in body
    variants = body["response_format"]["json_schema"]["schema"]["anyOf"]
    assert [v["properties"]["name"]["enum"] for v in variants] == [
        [t["function"]["name"]] for t in tools]
    assert variants[0]["properties"]["arguments"] == tools[0]["function"]["parameters"]
    system = body["messages"][0]
    assert system["role"] == "system"
    assert all(t["function"]["name"] in system["content"] for t in tools)
    assert system["content"].startswith("Route.")


def test_unknown_tool_name_or_bad_json_leaves_text_content(openai, monkeypatch):
    for content in ('{"name": "delete_everything", "arguments": {}}', "not json"):
        _capture_post(monkeypatch, _completion(content))
        reply = _run(llm_backend.post("/api/chat", {
            "messages": [{"role": "user", "content": "x"}], "tools": build_tools()}, timeout=5))
        assert reply["message"] == {"role": "assistant", "content": content}


def test_earlier_tool_call_is_replayed_as_json_text(openai, monkeypatch):
    seen = _capture_post(monkeypatch, _completion('{"name": "answer_kb_question", "arguments": {}}'))
    earlier = {"function": {"name": "route_banking_service", "arguments": {"category": "x", "service": "y"}}}
    _run(llm_backend.post("/api/chat", {"messages": [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [earlier]},
        {"role": "user", "content": "That path doesn't exist."},
    ], "tools": build_tools()}, timeout=5))
    assistant = seen["json"]["messages"][2]
    assert assistant["role"] == "assistant"
    assert json.loads(assistant["content"]) == {
        "name": "route_banking_service", "arguments": {"category": "x", "service": "y"}}


def test_http_error_propagates(openai, monkeypatch):
    async def fake_post(self, url, *args, **kwargs):
        return _Resp({}, status=400)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(httpx.HTTPStatusError):
        _run(llm_backend.post("/api/generate", {"prompt": "x"}, timeout=5))


# --- openai provider: streaming --------------------------------------------------


def _sse(*texts):
    lines = [": keep-alive", ""]
    for text in texts:
        lines += ["data: " + json.dumps({"choices": [{"delta": {"content": text}}]}), ""]
    return lines + ["data: [DONE]", ""]


@pytest.mark.parametrize("path,key", [("/api/chat", "message"), ("/api/generate", "response")])
def test_stream_translates_sse_to_ollama_chunks(openai, monkeypatch, path, key):
    seen = {}

    def fake_stream(self, method, url, *args, **kwargs):
        seen["url"], seen["json"] = url, kwargs.get("json")
        return _Stream(_sse("Hel", "", "lo"))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    async def go():
        payload = {"messages": [{"role": "user", "content": "x"}], "prompt": "x"}
        return [c async for c in llm_backend.stream(path, payload, timeout=5)]

    chunks = _run(go())
    assert seen["url"] == "http://llm:8000/v1/chat/completions"
    assert seen["json"]["stream"] is True
    text = [(c[key]["content"] if key == "message" else c[key]) for c in chunks]
    assert text == ["Hel", "lo", ""]
    assert [c["done"] for c in chunks] == [False, False, True]


# --- health ------------------------------------------------------------------------


def test_healthy_checks_models_endpoint(openai, monkeypatch):
    seen = {}

    async def fake_get(self, url, *args, **kwargs):
        seen["url"] = url
        return _Resp({}, status=200)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    assert _run(llm_backend.healthy()) is True
    assert seen["url"] == "http://llm:8000/v1/models"


def test_healthy_false_when_unreachable(openai, monkeypatch):
    async def fake_get(self, url, *args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    assert _run(llm_backend.healthy()) is False


# --- per-turn usage stats ------------------------------------------------------------


def test_stats_collect_openai_usage(openai, monkeypatch):
    body = _completion("ok")
    body["usage"] = {"prompt_tokens": 1200, "completion_tokens": 30}
    _capture_post(monkeypatch, body)

    async def go():
        stats = llm_backend.start_turn_stats()
        await llm_backend.post("/api/generate", {"prompt": "a"}, timeout=5)
        body["usage"] = {"prompt_tokens": 800, "completion_tokens": 10}
        await llm_backend.post("/api/generate", {"prompt": "b"}, timeout=5)
        return stats

    stats = _run(go())
    assert (stats.calls, stats.prompt_tokens, stats.completion_tokens, stats.peak_prompt_tokens) == (2, 2000, 40, 1200)


def test_stats_collect_ollama_usage_and_stream_usage(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    _capture_post(monkeypatch, {"response": "{}", "done": True, "prompt_eval_count": 500, "eval_count": 7})
    lines = [json.dumps({"message": {"content": "Hi"}, "done": False}),
             json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 900, "eval_count": 20})]
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda self, *a, **k: _Stream(lines))

    async def go():
        stats = llm_backend.start_turn_stats()
        await llm_backend.post("/api/generate", {"prompt": "a"}, timeout=5)
        async for _ in llm_backend.stream("/api/chat", {"messages": []}, timeout=5):
            pass
        return stats

    stats = _run(go())
    assert (stats.calls, stats.prompt_tokens, stats.completion_tokens, stats.peak_prompt_tokens) == (2, 1400, 27, 900)


def test_openai_stream_asks_for_usage_and_records_it(openai, monkeypatch):
    seen = {}
    lines = _sse("Hi")[:-2] + ["data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": 321, "completion_tokens": 4}}),
                               "", "data: [DONE]", ""]

    def fake_stream(self, method, url, *args, **kwargs):
        seen["json"] = kwargs.get("json")
        return _Stream(lines)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    async def go():
        stats = llm_backend.start_turn_stats()
        chunks = [c async for c in llm_backend.stream("/api/chat", {"messages": [{"role": "user", "content": "x"}]}, timeout=5)]
        return stats, chunks

    stats, chunks = _run(go())
    assert seen["json"]["stream_options"] == {"include_usage": True}
    assert [c["message"]["content"] for c in chunks] == ["Hi", ""]
    assert (stats.calls, stats.peak_prompt_tokens, stats.completion_tokens) == (1, 321, 4)


def test_no_stats_collected_outside_a_turn(openai, monkeypatch):
    _capture_post(monkeypatch, _completion("ok"))
    _run(llm_backend.post("/api/generate", {"prompt": "a"}, timeout=5))  # must not raise


def test_context_window_from_server_then_cached(openai, monkeypatch):
    monkeypatch.setattr(llm_backend, "_context_window", None)
    monkeypatch.setattr(settings, "LLM_CONTEXT_WINDOW", 0)
    calls = []

    async def fake_get(self, url, *args, **kwargs):
        calls.append(url)
        return _Resp({"data": [{"id": "other", "max_model_len": 4096}, {"id": "gemma4", "max_model_len": 8192}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    assert _run(llm_backend.context_window()) == 8192
    assert _run(llm_backend.context_window()) == 8192
    assert calls == ["http://llm:8000/v1/models"]


def test_context_window_override_and_ollama_default(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CONTEXT_WINDOW", 16000)
    assert _run(llm_backend.context_window()) == 16000
    monkeypatch.setattr(settings, "LLM_CONTEXT_WINDOW", 0)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    assert _run(llm_backend.context_window()) == settings.OLLAMA_NUM_CTX


# --- native tool calling (LLM_TOOL_MODE) ------------------------------------------------

_NATIVE_TOOLS = [{"type": "function", "function": {"name": "route", "description": "route it",
                                                   "parameters": {"type": "object", "properties": {"service": {"type": "string"}}}}}]


@pytest.mark.parametrize("mode, choice", [("native_auto", "auto"), ("native_required", "required")])
def test_native_mode_sends_server_tools_and_reads_tool_calls(openai, monkeypatch, mode, choice):
    monkeypatch.setattr(settings, "LLM_TOOL_MODE", mode)
    body = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "route", "arguments": '{"service": "balance"}'}},
        {"id": "c2", "type": "function", "function": {"name": "not_offered", "arguments": "{}"}},
    ]}}]}
    seen = _capture_post(monkeypatch, body)
    out = _run(llm_backend.post("/api/chat", {"messages": [{"role": "system", "content": "S"},
                                                          {"role": "user", "content": "bal"}],
                                              "tools": _NATIVE_TOOLS}, timeout=5))
    sent = seen["json"]
    assert sent["tools"] == _NATIVE_TOOLS and sent["tool_choice"] == choice
    assert "response_format" not in sent
    assert all("You have these tools" not in str(m["content"]) for m in sent["messages"])
    assert out["message"]["tool_calls"] == [{"function": {"name": "route", "arguments": {"service": "balance"}}}]


def test_native_mode_falls_back_to_json_text_and_bad_arguments(openai, monkeypatch):
    monkeypatch.setattr(settings, "LLM_TOOL_MODE", "native_auto")
    _capture_post(monkeypatch, {"choices": [{"message": {"content": '{"name": "route", "arguments": {"service": "x"}}'}}]})
    out = _run(llm_backend.post("/api/chat", {"messages": [{"role": "user", "content": "x"}], "tools": _NATIVE_TOOLS}, timeout=5))
    assert out["message"]["tool_calls"] == [{"function": {"name": "route", "arguments": {"service": "x"}}}]
    assert llm_backend._native_tool_calls(
        [{"function": {"name": "route", "arguments": "not json"}}], _NATIVE_TOOLS) == [{"function": {"name": "route", "arguments": {}}}]


def test_emulated_is_the_default(openai):
    assert settings.LLM_TOOL_MODE == "emulated"
    body = llm_backend._to_openai("/api/chat", {"messages": [{"role": "user", "content": "x"}], "tools": _NATIVE_TOOLS})
    assert "tools" not in body and body["response_format"]["type"] == "json_schema"
