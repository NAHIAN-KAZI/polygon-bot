"""Black-box regression tests for POST /chat against INTEGRATION.md (TASKS.md T-17).

INTEGRATION.md is the authoritative, external-team-facing contract doc for
this endpoint. These tests treat it as the spec and verify the endpoint's
*observable* behavior conforms to it end-to-end -- they deliberately do not
re-test internal branching already locked in by test_chat_regression.py
(pre-extension KB contract), test_chat_contract_extension.py (T-14's
ChatRequest field extension), or test_chat_banking_flow.py (T-15/T-16's
per-branch flow + audit wiring). Where those files already cover a scenario
thoroughly, this file only asserts the contract-level claim INTEGRATION.md
makes about it.

Mocking follows the same fake-installation pattern used throughout this
test suite: fakes are installed via monkeypatch.setattr on app.routes.chat's
imported names (chat_module.<name>), never on the real Ollama/Qdrant/session
store.
"""
import json

import httpx

import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterResult, AdapterUnavailableError
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification, KbQuestion, UnknownService

from tests.conftest import AUTH_HEADERS

CUSTOMER_ID = "cust-contract-1"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


async def _fake_embed_text(message, client=None):
    return [0.1] * 384


def _fake_search(vector, top_k):
    return []


async def _fake_stream_generate(prompt):
    for token in ("Hello", " world"):
        yield token


def _install_kb_fakes(monkeypatch):
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", _fake_search)
    monkeypatch.setattr(chat_module, "stream_generate", _fake_stream_generate)


def _install_session_fakes(monkeypatch):
    """Isolate get_session/record_turn from the real module-level session
    store so tests don't leak state into each other (same helper as
    test_chat_banking_flow.py)."""
    monkeypatch.setattr(chat_module, "get_session", lambda customer_id: [])

    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))

    record.calls = calls
    monkeypatch.setattr(chat_module, "record_turn", record)
    return record


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


# --- 1. plain KB question: token...done, `result` NEVER sent ----------------


def test_plain_kb_question_never_emits_result_event(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "What is the refund policy?"},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]

    assert event_names == ["token", "token", "done"]
    assert "result" not in event_names


# --- 2. all 5 result.type values, exact field-population rules --------------


def test_result_type_clarification_required_all_fields_null(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return Clarification(question="Which account would you like to check?")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "check my thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")

    assert result_event["type"] == "CLARIFICATION_REQUIRED"
    assert result_event["category"] is None
    assert result_event["service"] is None
    assert result_event["subservice"] is None
    assert result_event["payload"] is None
    assert result_event["routing"] is None
    assert result_event["version"] == "1.0"


def test_result_type_auth_required_taxonomy_populated_payload_routing_null(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="checking")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)

    # No Authorization header -> no customer identity -> AUTH_REQUIRED.
    resp = client.post("/chat", json={"message": "what's my balance"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")

    assert result_event["type"] == "AUTH_REQUIRED"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"
    assert result_event["subservice"] == "checking"
    assert result_event["payload"] is None
    assert result_event["routing"] is None
    assert result_event["version"] == "1.0"


def test_result_type_unknown_service_taxonomy_populated_payload_routing_null(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return UnknownService(category="not_a_real_cat", service="not_a_real_svc", subservice="sub")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "do the unknown thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")

    assert result_event["type"] == "UNKNOWN_SERVICE"
    assert result_event["category"] == "not_a_real_cat"
    assert result_event["service"] == "not_a_real_svc"
    assert result_event["subservice"] == "sub"
    assert result_event["payload"] is None
    assert result_event["routing"] is None
    assert result_event["version"] == "1.0"


def test_result_type_service_unavailable_taxonomy_populated_payload_routing_null(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="checking")

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterUnavailableError

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")

    assert result_event["type"] == "SERVICE_UNAVAILABLE"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"
    assert result_event["subservice"] == "checking"
    assert result_event["payload"] is None
    assert result_event["routing"] is None
    assert result_event["version"] == "1.0"


def test_result_type_banking_service_payload_and_routing_populated(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="checking")

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    fulfillment_data = {"balance": 1234.56, "currency": "USD"}

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=fulfillment_data)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")

    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"
    assert result_event["subservice"] == "checking"
    # payload carries the raw fulfillment data.
    assert result_event["payload"] == fulfillment_data
    # routing echoes category/service/subservice plus action: "redirect".
    assert result_event["routing"] == {
        "category": "account_info",
        "service": "balance",
        "subservice": "checking",
        "action": "redirect",
    }
    assert result_event["version"] == "1.0"


# --- 3. session_id is accepted but has no effect on behavior ----------------


def test_session_id_does_not_affect_behavior(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="checking")

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    fulfillment_data = {"balance": 42.0}

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=fulfillment_data)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp_a = client.post(
        "/chat",
        json={"message": "what's my balance", "session_id": "session-aaaa"},
        headers=JWT_HEADERS,
    )
    resp_b = client.post(
        "/chat",
        json={"message": "what's my balance", "session_id": "session-zzzz-different"},
        headers=JWT_HEADERS,
    )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    events_a = _parse_sse(resp_a.text)
    events_b = _parse_sse(resp_b.text)

    result_a = next(data for name, data in events_a if name == "result")
    result_b = next(data for name, data in events_b if name == "result")

    # Same identity, same message, different session_id -> identical outcome.
    # Behavior is governed by Authorization/JWT identity, not session_id.
    assert result_a == result_b
    assert result_a["type"] == "BANKING_SERVICE"


def test_session_id_does_not_affect_kb_path(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)

    resp_a = client.post(
        "/chat",
        json={"message": "What is the refund policy?", "session_id": "one"},
        headers=AUTH_HEADERS,
    )
    resp_b = client.post(
        "/chat",
        json={"message": "What is the refund policy?", "session_id": "two"},
        headers=AUTH_HEADERS,
    )

    events_a = [name for name, _ in _parse_sse(resp_a.text)]
    events_b = [name for name, _ in _parse_sse(resp_b.text)]

    assert events_a == events_b == ["token", "token", "done"]


# --- 4. category+service present skips classify() (FR-ROUTE-04) ------------


def test_category_and_service_present_skips_classify(client, monkeypatch):
    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={
            "message": "balance please",
            "category": "account_info",
            "service": "balance",
        },
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    assert classify_calls == []


def test_category_and_service_absent_invokes_classify(client, monkeypatch):
    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "balance please"},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    assert classify_calls == ["balance please"]


# --- 5. KB-path `error` event behavior is unchanged --------------------------


class _FakeRejectionResponse:
    text = "chunk too long"


def test_kb_path_embedding_model_rejection_emits_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_embed_text_rejects(message, client=None):
        raise httpx.HTTPStatusError("bad request", request=None, response=_FakeRejectionResponse())

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", fake_embed_text_rejects)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "What is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["error"]
    error_event = events[0][1]
    assert "Embedding model rejected the request" in error_event["detail"]
    assert "chunk too long" in error_event["detail"]


def test_kb_path_embedding_model_unreachable_emits_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_embed_text_unreachable(message, client=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", fake_embed_text_unreachable)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "What is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["detail"] == "Embedding model (Ollama) is unreachable"


def test_kb_path_vector_store_unreachable_emits_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    def fake_search_unreachable(vector, top_k):
        raise RuntimeError("qdrant connection reset")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", fake_search_unreachable)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "What is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["detail"] == "Vector store (Qdrant) is unreachable"


def test_kb_path_generation_model_failure_mid_stream_emits_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_stream_generate_fails(prompt):
        yield "partial"
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", _fake_search)
    monkeypatch.setattr(chat_module, "stream_generate", fake_stream_generate_fails)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "What is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]
    assert event_names[-1] == "error"
    assert event_names.count("token") == 1

    error_event = next(data for name, data in events if name == "error")
    assert error_event["detail"] == "Generation model (Ollama) failed or became unreachable mid-stream"


# --- 6. GET /health response shape --------------------------------------


def test_health_response_shape_matches_integration_doc(client, monkeypatch):
    import app.main as main_module

    async def fake_check_ollama():
        return True

    def fake_check_qdrant():
        return True

    monkeypatch.setattr(main_module, "check_ollama", fake_check_ollama)
    monkeypatch.setattr(main_module, "check_qdrant", fake_check_qdrant)

    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"status", "ollama", "qdrant"}
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["ollama"], bool)
    assert isinstance(body["qdrant"], bool)
