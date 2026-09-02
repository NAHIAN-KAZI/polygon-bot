"""Tests for the banking-service wiring in app/routes/chat.py (TASKS.md T-15).

Covers the branches _chat_stream() dispatches to based on the classification
result: Clarification, UnknownService, BankingService (with/without identity,
adapter success/failure), and the direct category+service routing path that
bypasses classify() entirely. classify/is_valid_path/extract_jwt/verify_jwt/
get_session/record_turn/fulfill_banking_service are mocked at their
app.routes.chat import sites, following the same monkeypatch style as
test_chat_regression.py and test_chat_contract_extension.py, so nothing here
touches real Ollama, the taxonomy cache, or the real in-memory session store.
"""
import json

import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterAuthError, AdapterResult, AdapterUnavailableError
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification, KbQuestion, UnknownService

from tests.conftest import AUTH_HEADERS

CUSTOMER_ID = "cust-123"
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


def _spy():
    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))

    record.calls = calls
    return record


def _install_session_fakes(monkeypatch):
    """Isolate get_session/record_turn from the real module-level session
    store so tests don't leak state into each other."""
    monkeypatch.setattr(chat_module, "get_session", lambda customer_id: [])
    record_turn_spy = _spy()
    monkeypatch.setattr(chat_module, "record_turn", record_turn_spy)
    return record_turn_spy


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


def test_clarification_yields_question_then_result(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return Clarification(question="Which account would you like to check?")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "check my thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "Which account would you like to check?"

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"
    assert result_event["category"] is None
    assert result_event["service"] is None
    assert result_event["subservice"] is None
    assert result_event["payload"] is None
    assert result_event["routing"] is None

    assert record_turn_spy.calls == []


def test_unknown_service_yields_message_then_result(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return UnknownService(category="x", service="y", subservice=None)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "do the thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "I'm not able to help with that specific request right now."

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "UNKNOWN_SERVICE"
    assert result_event["category"] == "x"
    assert result_event["service"] == "y"
    assert result_event["subservice"] is None
    assert result_event["payload"] is None
    assert result_event["routing"] is None

    assert record_turn_spy.calls == []


def test_banking_service_without_identity_requires_auth(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    fulfill_calls = []

    async def fake_fulfill(*args, **kwargs):
        fulfill_calls.append((args, kwargs))
        return AdapterResult(data={})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "Please log in to continue with this request."

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "AUTH_REQUIRED"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"
    assert result_event["subservice"] is None
    assert result_event["payload"] is None
    assert result_event["routing"] is None

    assert fulfill_calls == []
    assert record_turn_spy.calls == []


def test_banking_service_adapter_auth_error_requires_auth(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    fulfill_calls = []

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((customer_identity, jwt, category, service, subservice, payload))
        raise AdapterAuthError

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "Please log in to continue with this request."

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "AUTH_REQUIRED"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"
    assert result_event["payload"] is None
    assert result_event["routing"] is None

    assert len(fulfill_calls) == 1


def test_banking_service_adapter_unavailable_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

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
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "That service isn't available right now. Please try again shortly."

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "SERVICE_UNAVAILABLE"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"


def test_banking_service_mock_adapter_success(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="pay_transfer", service="transfer_funds", subservice="internal")

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    mock_data = {"mock": True, "subservice": "internal", "note": "synthetic"}

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=mock_data)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "transfer money"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "Sure — here's information about transfer funds."

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == mock_data
    assert result_event["routing"] == {
        "category": "pay_transfer",
        "service": "transfer_funds",
        "subservice": "internal",
        "action": "redirect",
    }


def test_banking_service_real_adapter_balance_success(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="balance")

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert "500.00" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == {"balance": "500.00"}


def test_direct_taxonomy_routing_skips_classify(client, monkeypatch):
    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "is_valid_path", lambda category, service, subservice=None: True)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "balance please", "category": "account_info", "service": "balance"},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "AUTH_REQUIRED"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"

    assert classify_calls == []


def test_record_turn_called_for_kb_question_with_identity(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    _install_kb_fakes(monkeypatch)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(record_turn_spy.calls) == 1
    args, kwargs = record_turn_spy.calls[0]
    customer_id, turn = args
    assert customer_id == CUSTOMER_ID
    assert turn.message == "what is the refund policy?"
    assert turn.classification is None


def test_record_turn_called_for_banking_service_with_identity(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="balance")

    def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(record_turn_spy.calls) == 1
    args, kwargs = record_turn_spy.calls[0]
    customer_id, turn = args
    assert customer_id == CUSTOMER_ID
    assert turn.message == "what's my balance"
    assert turn.classification == {
        "type": "BANKING_SERVICE",
        "category": "account_info",
        "service": "balance",
        "subservice": "balance",
    }


def test_record_turn_not_called_without_identity(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert record_turn_spy.calls == []


def test_kb_path_matches_pre_t15_contract(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]

    assert "result" not in event_names
    assert event_names.count("token") == 2
    assert event_names[-1] == "done"
