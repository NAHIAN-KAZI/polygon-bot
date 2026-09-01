"""Regression tests for the pre-banking-extension behavior of POST /chat.

These pin down the documented contract in INTEGRATION.md: a token/done SSE
stream with no sources event (removed) and no result event (not yet added).
Ollama (embedding + generation) and Qdrant are mocked at the call sites used
by app/routes/chat.py so these run fast and deterministically without a live
GPU/vector-store stack.
"""
import json

import app.routes.chat as chat_module

from tests.conftest import AUTH_HEADERS


async def _fake_embed_text(message, client=None):
    return [0.1] * 384


def _fake_search(vector, top_k):
    return []


async def _fake_stream_generate(prompt):
    for token in ("Hello", " world"):
        yield token


def _install_fakes(monkeypatch):
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", _fake_search)
    monkeypatch.setattr(chat_module, "stream_generate", _fake_stream_generate)


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip("\n").split("\n\n"):
        if not block.strip():
            continue
        event_name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event_name, data))
    return events


def test_chat_success_streams_tokens_then_done_with_no_sources_or_result(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "What is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]

    assert event_names.count("token") == 2
    assert event_names[-1] == "done"
    assert "sources" not in event_names
    assert "result" not in event_names

    tokens = "".join(data["token"] for name, data in events if name == "token")
    assert tokens == "Hello world"


def test_chat_without_api_key_returns_401(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "What is the refund policy?"})

    assert resp.status_code == 401


def test_chat_blank_message_returns_422(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "   "}, headers=AUTH_HEADERS)

    assert resp.status_code == 422


def test_chat_missing_message_field_returns_422(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post("/chat", json={}, headers=AUTH_HEADERS)

    assert resp.status_code == 422
