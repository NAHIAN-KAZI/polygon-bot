"""Tests for the ChatRequest schema extension (TASKS.md T-14).

Covers the four new optional fields (`category`, `service`, `subservice`,
`payload`) added to the `/chat` request body. The route handler does not
consume these fields yet -- this is schema-only coverage. Ollama (embedding
+ generation) and Qdrant are mocked the same way as test_chat_regression.py.
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


def test_message_only_still_returns_200_sse_stream(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "What is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]
    assert event_names.count("token") == 2
    assert event_names[-1] == "done"


def test_all_new_fields_populated_is_accepted_and_streams(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={
            "message": "What is the refund policy?",
            "category": "billing",
            "service": "payments",
            "subservice": "refunds",
            "payload": {"order_id": "abc123", "amount": 42.5},
        },
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]
    assert event_names.count("token") == 2
    assert event_names[-1] == "done"


def test_payload_accepts_arbitrary_nested_structure(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={
            "message": "What is the refund policy?",
            "payload": {"nested": {"a": [1, 2, 3]}, "flag": True},
        },
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]
    assert event_names.count("token") == 2
    assert event_names[-1] == "done"


def test_taxonomy_fields_without_payload_is_accepted(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={
            "message": "What is the refund policy?",
            "category": "billing",
            "service": "payments",
            "subservice": "refunds",
        },
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]
    assert event_names.count("token") == 2
    assert event_names[-1] == "done"


def test_invalid_type_for_category_returns_422(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "What is the refund policy?", "category": 123},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 422


def test_missing_message_still_returns_422(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"category": "billing", "service": "payments"},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 422


def test_blank_message_still_returns_422(client, monkeypatch):
    _install_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "   ", "payload": {"a": 1}},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 422
