"""Tests for the banking-service wiring in app/routes/chat.py (TASKS.md T-15).

Covers the branches _chat_stream() dispatches to based on the classification
result: Clarification, UnknownService, BankingService (with/without identity,
adapter success/failure), and the direct category+service routing path that
bypasses classify() entirely. classify/is_valid_path/extract_jwt/verify_jwt/
get_classification_context/record_turn/fulfill_banking_service are mocked at
their app.routes.chat import sites, following the same monkeypatch style as
test_chat_regression.py and test_chat_contract_extension.py, so nothing here
touches real Ollama, the taxonomy cache, or the real in-memory session store.

TASKS.md T-24: _chat_stream builds recent_turns via
session.get_classification_context(...) instead of the raw get_session(...)
(scoped to the pending-clarification case only, to avoid contaminating a
fresh classification with unrelated past turns). _install_session_fakes
patches get_classification_context accordingly.
"""
import asyncio
import copy
import json
from datetime import datetime, timezone

import httpx

import app.banking.audit as audit_module
import app.routes.chat as chat_module
from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterResult,
    AdapterUnavailableError,
)
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
    """Isolate get_classification_context/record_turn from the real
    module-level session store so tests don't leak state into each other."""
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])
    record_turn_spy = _spy()
    monkeypatch.setattr(chat_module, "record_turn", record_turn_spy)
    return record_turn_spy


def _install_audit_spy(monkeypatch):
    """Patch app.banking.audit.log_banking_turn at its call site in
    chat_module (T-16), so tests can assert it fires on every non-KB branch
    and never on a pure KB question, without emitting a real log line."""
    audit_spy = _spy()
    monkeypatch.setattr(chat_module.audit, "log_banking_turn", audit_spy)
    return audit_spy


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

    async def fake_verify_jwt(token):
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

    async def fake_verify_jwt(token):
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


_ACCOUNT_SELECTION_ACCOUNTS = [
    {"accountNumber": "111", "accountName": "Savings", "accountType": "SAVINGS", "balance": "100"},
    {"accountNumber": "222", "accountName": "Checking", "accountType": "CURRENT", "balance": "50"},
]


def test_banking_service_account_selection_required(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterAccountSelectionRequiredError(_ACCOUNT_SELECTION_ACCOUNTS)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "ACCOUNT_SELECTION_REQUIRED"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "balance"
    assert result_event["subservice"] is None
    assert result_event["payload"] == {"accounts": _ACCOUNT_SELECTION_ACCOUNTS}
    assert result_event["routing"] is None


def test_banking_service_mock_adapter_success(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="pay_transfer", service="transfer_funds", subservice="internal")

    async def fake_verify_jwt(token):
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

    async def fake_verify_jwt(token):
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
    assert result_event["payload"] == {"balance": "500.00", "balanceFormatted": "৳500"}


class _FakeOllamaResponse:
    """Minimal httpx.Response stand-in for mocking Ollama's /api/generate,
    matching tests/test_routing.py's FakeResponse pattern."""

    def __init__(self, json_data):
        self._json_data = json_data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_data


def test_banking_service_real_adapter_success_uses_synthesized_reply(client, monkeypatch):
    """TASKS.md T-29: the real-adapter (non-mock) BANKING_SERVICE success
    branch now calls _synthesize_reply(...) instead of _subservice_reply(...)
    directly. This drives the full /chat SSE flow end-to-end with a mocked
    Ollama /api/generate call and confirms the LLM-synthesized text -- not
    the deterministic template -- is what actually reaches the token event."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="balance")

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"balance": "500.00"})

    async def fake_post(self, url, *args, **kwargs):
        return _FakeOllamaResponse({"response": "This is your distinctive synthesized reply 42."})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "This is your distinctive synthesized reply 42."

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == {"balance": "500.00", "balanceFormatted": "৳500"}


def test_banking_service_mock_adapter_never_calls_synthesize_reply(client, monkeypatch):
    """TASKS.md T-29: the data.get("mock") is True branch is unchanged --
    still the plain hardcoded template line -- and must never invoke
    _synthesize_reply (and therefore never hit Ollama) at all."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="pay_transfer", service="transfer_funds", subservice="internal")

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    mock_data = {"mock": True, "subservice": "internal", "note": "synthetic"}

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=mock_data)

    synth_calls = []

    async def fake_synthesize_reply(message, service, subservice, data):
        synth_calls.append((message, service, subservice, data))
        return "SHOULD NEVER APPEAR"

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "_synthesize_reply", fake_synthesize_reply)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "transfer money"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "Sure — here's information about transfer funds."

    assert synth_calls == []


def test_banking_service_device_history_wrapped_devices_no_crash(client, monkeypatch):
    """T-22 regression test: the real DeviceHistoryAdapter now wraps the bare
    array from GET /auth/v1/devices under a "devices" key before returning
    AdapterResult. Before the fix, a bare list flowed all the way to this
    success-path's data.get("mock") check and crashed with AttributeError.
    This locks in that /chat's SSE response completes cleanly with a valid
    BANKING_SERVICE result instead of crashing."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="device_history", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    devices_payload = {
        "devices": [
            {"id": 1, "deviceName": "iPhone"},
            {"id": 2, "deviceName": "Pixel"},
        ]
    }

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=devices_payload)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what devices are logged in?"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "device_history"
    assert result_event["payload"] == devices_payload


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

    async def fake_verify_jwt(token):
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

    async def fake_verify_jwt(token):
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


def test_record_turn_called_for_account_selection_required_with_identity(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterAccountSelectionRequiredError(_ACCOUNT_SELECTION_ACCOUNTS)

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
        "type": "ACCOUNT_SELECTION_REQUIRED",
        "category": "account_info",
        "service": "balance",
        "subservice": None,
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


# --- audit logging (TASKS.md T-16): audit.log_banking_turn must fire on ------
# --- every non-KB branch and never for a pure KB question -------------------


def test_audit_not_called_for_pure_kb_question(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert audit_spy.calls == []


def test_audit_called_once_for_clarification(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return Clarification(question="Which account would you like to check?")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "check my thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    identity, turn_classification = args
    assert identity is None
    assert turn_classification["type"] == "CLARIFICATION_REQUIRED"


def test_audit_called_once_for_unknown_service(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return UnknownService(category="x", service="y", subservice=None)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "do the thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    identity, turn_classification = args
    assert turn_classification["type"] == "UNKNOWN_SERVICE"
    assert turn_classification["category"] == "x"
    assert turn_classification["service"] == "y"


def test_audit_called_once_for_banking_service_without_identity(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    async def fake_fulfill(*args, **kwargs):
        return AdapterResult(data={})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    identity, turn_classification = args
    assert identity is None
    assert turn_classification["type"] == "AUTH_REQUIRED"


def test_audit_called_once_for_adapter_auth_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterAuthError

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    identity, turn_classification = args
    assert identity == CustomerIdentity(customer_id=CUSTOMER_ID)
    assert turn_classification["type"] == "AUTH_REQUIRED"


def test_audit_called_once_for_service_unavailable(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterUnavailableError

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    _, turn_classification = args
    assert turn_classification["type"] == "SERVICE_UNAVAILABLE"


def test_audit_called_once_for_account_selection_required(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterAccountSelectionRequiredError(_ACCOUNT_SELECTION_ACCOUNTS)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    _, turn_classification = args
    assert turn_classification["type"] == "ACCOUNT_SELECTION_REQUIRED"


def test_audit_called_once_for_banking_service_success(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="balance")

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    identity, turn_classification = args
    assert identity == CustomerIdentity(customer_id=CUSTOMER_ID)
    assert turn_classification["type"] == "BANKING_SERVICE"
    assert kwargs["latency_ms"] >= 0


# --- recent_turns wiring (TASKS.md T-24): _chat_stream must build ------------
# --- recent_turns via session.get_classification_context (scoped to the -----
# --- pending-clarification case), not the raw get_session, and only when ----
# --- a customer_identity was resolved from the JWT. --------------------------


def test_chat_stream_calls_get_classification_context_with_customer_id_when_identity_present(client, monkeypatch):
    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    context_calls = []

    def fake_get_classification_context(customer_id):
        context_calls.append(customer_id)
        return []

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "get_classification_context", fake_get_classification_context)
    monkeypatch.setattr(chat_module, "record_turn", _spy())
    _install_kb_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert context_calls == [CUSTOMER_ID]


def test_chat_stream_does_not_call_get_classification_context_without_identity(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    context_calls = []

    def fake_get_classification_context(customer_id):
        context_calls.append(customer_id)
        return []

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "get_classification_context", fake_get_classification_context)
    monkeypatch.setattr(chat_module, "record_turn", _spy())
    _install_kb_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert context_calls == []


# --- masking/formatting enrichment (TASKS.md T-32): _mask_number, ----------
# --- _format_bdt, and _enrich_payload additively decorate real-adapter -----
# --- payloads with display-friendly fields, only for the non-mock branch. --


def test_mask_number_masks_all_but_last_four():
    assert chat_module._mask_number("1234567890") == "••••••7890"


def test_mask_number_custom_keep():
    assert chat_module._mask_number("1234567890", keep=2) == "••••••••90"


def test_mask_number_shorter_than_keep_returns_as_is():
    assert chat_module._mask_number("123", keep=4) == "123"


def test_mask_number_equal_to_keep_returns_as_is():
    assert chat_module._mask_number("1234", keep=4) == "1234"


def test_mask_number_empty_string_returns_none():
    assert chat_module._mask_number("", keep=4) is None


def test_mask_number_none_input_returns_none():
    assert chat_module._mask_number(None) is None


def test_format_bdt_int():
    assert chat_module._format_bdt(5000) == "৳5,000"


def test_format_bdt_float_rounds_to_whole_taka():
    assert chat_module._format_bdt(5000.4) == "৳5,000"


def test_format_bdt_numeric_string():
    assert chat_module._format_bdt("500.00") == "৳500"


def test_format_bdt_adds_thousands_separators():
    assert chat_module._format_bdt(1234567) == "৳1,234,567"


def test_format_bdt_non_numeric_string_returns_none():
    assert chat_module._format_bdt("not a number") is None


def test_format_bdt_none_returns_none():
    assert chat_module._format_bdt(None) is None


def test_enrich_payload_balance_adds_formatted_field_keeps_raw():
    data = {"balance": "500.00", "currency": "BDT"}
    result = chat_module._enrich_payload("balance", "balance", data)

    assert result["balance"] == "500.00"
    assert result["currency"] == "BDT"
    assert result["balanceFormatted"] == "৳500"
    # original untouched (additive, deep-copied)
    assert data == {"balance": "500.00", "currency": "BDT"}


def test_enrich_payload_accounts_adds_masked_and_formatted_fields():
    data = {
        "data": {
            "accounts": [
                {"accountNumber": "1234567890", "accountType": "SAVINGS"},
                {"accountNumber": "5555", "accountType": "CURRENT"},
            ],
            "ledgerAccounts": [
                {"identifier": "9876543210", "balance": "2500.00"},
            ],
        }
    }
    original_copy = copy.deepcopy(data)

    result = chat_module._enrich_payload("accounts", None, data)

    accounts = result["data"]["accounts"]
    assert accounts[0]["accountNumber"] == "1234567890"
    assert accounts[0]["accountNumberMasked"] == "••••••7890"
    assert accounts[1]["accountNumber"] == "5555"
    assert accounts[1]["accountNumberMasked"] == "5555"

    ledger = result["data"]["ledgerAccounts"][0]
    assert ledger["identifier"] == "9876543210"
    assert ledger["identifierMasked"] == "••••••3210"
    assert ledger["balance"] == "2500.00"
    assert ledger["balanceFormatted"] == "৳2,500"

    # original input untouched
    assert data == original_copy


def test_enrich_payload_transaction_history_adds_masked_and_formatted_fields():
    data = {
        "transactions": [
            {"accountNumber": "1234567890", "amount": "150.75", "description": "Groceries"},
        ],
        "pagination": {"totalCount": 1},
    }
    original_copy = copy.deepcopy(data)

    result = chat_module._enrich_payload("transaction_history", None, data)

    txn = result["transactions"][0]
    assert txn["accountNumber"] == "1234567890"
    assert txn["accountNumberMasked"] == "••••••7890"
    assert txn["amount"] == "150.75"
    assert txn["amountFormatted"] == "৳151"
    assert result["pagination"] == {"totalCount": 1}

    assert data == original_copy


def test_enrich_payload_device_history_passes_through_unchanged():
    data = {"devices": [{"id": 1, "deviceName": "iPhone"}]}
    result = chat_module._enrich_payload("device_history", None, data)
    assert result == data


def test_enrich_payload_login_history_passes_through_unchanged():
    data = {"records": [{"status": "SUCCESS", "ipAddress": "1.2.3.4"}]}
    result = chat_module._enrich_payload("login_history", None, data)
    assert result == data


def test_enrich_payload_unrecognized_key_passes_through_unchanged():
    data = {"anything": "goes here"}
    result = chat_module._enrich_payload("some_other_service", "some_other_subservice", data)
    assert result == data


def test_enrich_payload_accounts_missing_inner_data_key_no_crash():
    data = {"unexpected": "shape"}
    result = chat_module._enrich_payload("accounts", None, data)
    assert result == data


def test_enrich_payload_accounts_malformed_entries_no_crash():
    data = {
        "data": {
            "accounts": ["not-a-dict", 123, None],
            "ledgerAccounts": "not-a-list",
        }
    }
    result = chat_module._enrich_payload("accounts", None, data)
    assert result["data"]["accounts"] == ["not-a-dict", 123, None]
    assert result["data"]["ledgerAccounts"] == "not-a-list"


def test_enrich_payload_balance_non_dict_data_no_crash():
    result = chat_module._enrich_payload("balance", "balance", "not-a-dict")
    assert result == "not-a-dict"


def test_enrich_payload_transaction_history_missing_transactions_key_no_crash():
    data = {"pagination": {"totalCount": 0}}
    result = chat_module._enrich_payload("transaction_history", None, data)
    assert result == data


def test_banking_service_real_adapter_accounts_success_enriches_payload(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="accounts", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    accounts_data = {
        "data": {
            "accounts": [{"accountNumber": "1234567890", "accountType": "SAVINGS"}],
            "ledgerAccounts": [{"identifier": "9876543210", "balance": "2500.00"}],
        }
    }

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=accounts_data)

    async def fake_synthesize_reply(message, service, subservice, data):
        return "Here are your accounts."

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "_synthesize_reply", fake_synthesize_reply)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my accounts"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"

    payload = result_event["payload"]
    account = payload["data"]["accounts"][0]
    assert account["accountNumber"] == "1234567890"
    assert account["accountNumberMasked"] == "••••••7890"
    ledger = payload["data"]["ledgerAccounts"][0]
    assert ledger["identifierMasked"] == "••••••3210"
    assert ledger["balanceFormatted"] == "৳2,500"


def test_banking_service_real_adapter_balance_success_enriches_payload(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="balance")

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"balance": "500.00"})

    async def fake_synthesize_reply(message, service, subservice, data):
        return "Your balance is ৳500."

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "_synthesize_reply", fake_synthesize_reply)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    payload = result_event["payload"]
    assert payload["balance"] == "500.00"
    assert payload["balanceFormatted"] == "৳500"


def test_banking_service_real_adapter_transaction_history_success_enriches_payload(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="transaction_history", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    txn_data = {
        "transactions": [
            {"accountNumber": "1234567890", "amount": "150.75", "description": "Groceries", "type": "DEBIT"},
        ],
        "pagination": {"totalCount": 1},
    }

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=txn_data)

    async def fake_synthesize_reply(message, service, subservice, data):
        return "Here are your recent transactions."

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "_synthesize_reply", fake_synthesize_reply)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my recent transactions"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    payload = result_event["payload"]
    txn = payload["transactions"][0]
    assert txn["accountNumberMasked"] == "••••••7890"
    assert txn["amountFormatted"] == "৳151"


def test_banking_service_mock_adapter_payload_not_enriched(client, monkeypatch):
    """The mock-adapter branch must remain exactly as before T-32: _enrich_payload
    is never invoked and the result payload is untouched."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="pay_transfer", service="transfer_funds", subservice="internal")

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    mock_data = {"mock": True, "subservice": "internal", "note": "synthetic"}

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=mock_data)

    enrich_calls = []
    real_enrich_payload = chat_module._enrich_payload

    def spy_enrich_payload(service, subservice, data):
        enrich_calls.append((service, subservice, data))
        return real_enrich_payload(service, subservice, data)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "_enrich_payload", spy_enrich_payload)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "transfer money"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["payload"] == mock_data
    assert enrich_calls == []


# --- prompt redaction (TASKS.md T-35): _redact_for_prompt strips/masks -----
# --- sensitive raw fields before data is embedded in the LLM prompt, --------
# --- without ever mutating the input or affecting the result payload. -------


def test_redact_for_prompt_account_number_replaced_with_masked_sibling():
    data = {"accountNumber": "1234567890", "accountNumberMasked": "••••••7890"}
    result = chat_module._redact_for_prompt(data)
    assert result["accountNumber"] == "••••••7890"


def test_redact_for_prompt_account_number_without_masked_sibling_falls_back():
    data = {"accountNumber": "1234567890"}
    result = chat_module._redact_for_prompt(data)
    assert result["accountNumber"] == "[masked]"


def test_redact_for_prompt_identifier_replaced_with_masked_sibling():
    data = {"identifier": "9876543210", "identifierMasked": "••••••3210"}
    result = chat_module._redact_for_prompt(data)
    assert result["identifier"] == "••••••3210"


def test_redact_for_prompt_identifier_without_masked_sibling_falls_back():
    data = {"identifier": "9876543210"}
    result = chat_module._redact_for_prompt(data)
    assert result["identifier"] == "[masked]"


def test_redact_for_prompt_cif_number_always_redacted():
    data = {"cifNumber": "CIF-000111", "accountNumber": "1234567890", "accountNumberMasked": "••••••7890"}
    result = chat_module._redact_for_prompt(data)
    assert result["cifNumber"] == "[redacted]"
    assert result["accountNumber"] == "••••••7890"


def test_redact_for_prompt_nid_always_redacted():
    data = {"nid": "1234567890123"}
    result = chat_module._redact_for_prompt(data)
    assert result["nid"] == "[redacted]"


def test_redact_for_prompt_description_masks_embedded_long_digit_run():
    data = {"description": "Transfer to account 1234567890 for rent"}
    result = chat_module._redact_for_prompt(data)
    assert result["description"] == "Transfer to account ••••••7890 for rent"


def test_redact_for_prompt_from_to_account_masks_embedded_long_digit_run():
    data = {"fromToAccount": "9876543210"}
    result = chat_module._redact_for_prompt(data)
    assert result["fromToAccount"] == "••••••3210"


def test_redact_for_prompt_short_digit_run_left_alone():
    data = {"description": "Order #12345 confirmed"}
    result = chat_module._redact_for_prompt(data)
    assert result["description"] == "Order #12345 confirmed"


def test_redact_for_prompt_walks_list_of_transaction_dicts():
    data = {
        "transactions": [
            {"description": "Paid to 1112223334"},
            {"description": "Paid to 5556667778"},
        ]
    }
    result = chat_module._redact_for_prompt(data)
    assert result["transactions"][0]["description"] == "Paid to ••••••3334"
    assert result["transactions"][1]["description"] == "Paid to ••••••7778"


def test_redact_for_prompt_walks_deeply_nested_dicts():
    data = {"data": {"accounts": [{"accountNumber": "1234567890"}]}}
    result = chat_module._redact_for_prompt(data)
    assert result["data"]["accounts"][0]["accountNumber"] == "[masked]"


def test_redact_for_prompt_does_not_mutate_original_input():
    original = {
        "accountNumber": "1234567890",
        "accountNumberMasked": "••••••7890",
        "cifNumber": "CIF-000111",
        "nid": "1234567890123",
        "description": "Transfer to 1234567890",
        "nested": {"identifier": "9876543210"},
    }
    snapshot = copy.deepcopy(original)

    result = chat_module._redact_for_prompt(original)

    assert original == snapshot
    # sanity: redaction actually changed something in the returned copy
    assert result["accountNumber"] != original["accountNumber"]


def test_redact_for_prompt_adversarial_circular_reference_falls_back_to_original():
    data = {"accountNumber": "1234567890"}
    data["self"] = data  # circular reference: copy.deepcopy handles cycles fine,
    # but this locks in that a genuinely un-copyable/broken structure still
    # returns the original data rather than raising.

    class Uncopyable:
        def __deepcopy__(self, memo):
            raise RuntimeError("boom")

    data["broken"] = Uncopyable()

    result = chat_module._redact_for_prompt(data)
    assert result is data


def test_banking_service_real_adapter_success_prompt_redacted_payload_unchanged(client, monkeypatch):
    """Full /chat flow (TASKS.md T-35): the account number embedded in a
    `description` free-text field must never reach the Ollama prompt, but the
    `result` event's payload (built from the T-32 enriched data) must still
    carry the raw value alongside its masked/formatted siblings, unchanged
    from pre-T-35 behavior -- redaction is prompt-only."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="transaction_history", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    txn_data = {
        "transactions": [
            {
                "accountNumber": "1234567890",
                "amount": "150.75",
                "description": "Transfer to 9998887776 for rent",
                "type": "DEBIT",
            }
        ],
        "pagination": {"totalCount": 1},
    }

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=txn_data)

    captured_prompts = []

    async def fake_post(self, url, *args, **kwargs):
        captured_prompts.append(kwargs["json"]["prompt"])
        return _FakeOllamaResponse({"response": "You spent ৳151 on a transfer recently."})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my recent transactions"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    # the raw account number and the embedded digit run in `description`
    # must never have reached the LLM prompt.
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "1234567890" not in prompt
    assert "9998887776" not in prompt
    # json.dumps(..., default=str) escapes the non-ASCII "•" bullet, so look
    # for the JSON-encoded form rather than the literal character.
    assert json.dumps("••••••7890")[1:-1] in prompt  # accountNumberMasked substitute, added by T-32 _enrich_payload
    assert json.dumps("••••••7776")[1:-1] in prompt  # masked description digit run

    # the result payload must be raw + masked/formatted, exactly as T-32 left it.
    result_event = next(data for name, data in events if name == "result")
    txn = result_event["payload"]["transactions"][0]
    assert txn["accountNumber"] == "1234567890"
    assert txn["accountNumberMasked"] == "••••••7890"
    assert txn["amountFormatted"] == "৳151"
    assert txn["description"] == "Transfer to 9998887776 for rent"


# --- fallback-path redaction (TASKS.md T-35 follow-up): when the Ollama -----
# --- call in _synthesize_reply fails or returns empty text, it falls back --
# --- to the deterministic _subservice_reply template. Both fallback call ---
# --- sites must pass _redact_for_prompt(data) into _subservice_reply, not --
# --- the raw data, so the template's transaction_history branch (which -----
# --- embeds `description` verbatim) never leaks a full account number into-
# --- the customer-facing spoken reply. ---------------------------------------

_LEAKY_TXN_DATA = {
    "transactions": [
        {
            "accountNumber": "9876543210",
            "accountNumberMasked": "••••••3210",
            "amount": "100",
            "description": "bKash: From 100126000015 to 4600000",
            "type": "DEBIT",
        }
    ],
    "pagination": {"totalCount": 1},
}


def test_synthesize_reply_fallback_on_exception_redacts_description(monkeypatch):
    async def fake_post(self, url, *args, **kwargs):
        raise httpx.ConnectTimeout("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    reply = asyncio.run(
        chat_module._synthesize_reply(
            "show my recent transactions", "account_info", "transaction_history", copy.deepcopy(_LEAKY_TXN_DATA)
        )
    )

    assert "100126000015" not in reply
    assert "4600000" not in reply
    assert "••••••••0015" in reply
    assert "•••0000" in reply


def test_synthesize_reply_fallback_on_empty_response_redacts_description(monkeypatch):
    async def fake_post(self, url, *args, **kwargs):
        return _FakeOllamaResponse({"response": ""})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    reply = asyncio.run(
        chat_module._synthesize_reply(
            "show my recent transactions", "account_info", "transaction_history", copy.deepcopy(_LEAKY_TXN_DATA)
        )
    )

    assert "100126000015" not in reply
    assert "4600000" not in reply
    assert "••••••••0015" in reply
    assert "•••0000" in reply


def test_chat_stream_fallback_redacts_token_but_not_payload(client, monkeypatch):
    """Full /chat flow: Ollama fails, so the spoken `token` text falls back to
    _subservice_reply -- but it must receive redacted data, so the raw
    description embedding a full account number never reaches the customer.
    The `result` event's `payload` is unaffected (still raw + masked/formatted,
    exactly as T-32 enrichment left it) since redaction is spoken-reply-only."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="transaction_history", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=copy.deepcopy(_LEAKY_TXN_DATA))

    async def fake_post(self, url, *args, **kwargs):
        raise httpx.ConnectTimeout("boom")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my recent transactions"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert "100126000015" not in token_event["token"]
    assert "4600000" not in token_event["token"]
    assert "••••••••0015" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    txn = result_event["payload"]["transactions"][0]
    assert txn["accountNumber"] == "9876543210"
    assert txn["accountNumberMasked"] == "••••••3210"
    assert txn["description"] == "bKash: From 100126000015 to 4600000"
    assert txn["amountFormatted"] == "৳100"


def test_chat_stream_passes_get_classification_context_result_into_classify(client, monkeypatch):
    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    sentinel_turns = [
        chat_module.ChatTurn(
            timestamp=datetime.now(timezone.utc),
            message="which account?",
            classification={"type": "CLARIFICATION_REQUIRED"},
        )
    ]

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: sentinel_turns)
    monkeypatch.setattr(chat_module, "record_turn", _spy())

    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(recent_turns)
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "savings"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert classify_calls == [sentinel_turns]


# --- operational logging (TASKS.md T-36): chat.requests logger ---------------
# --- (request-entry log, KB-path stage logs, banking-path per-branch logs) ---
# --- and audit.log_banking_turn's new request_id kwarg -----------------------


def _install_chat_logger_spy(monkeypatch):
    """Capture every chat_module.logger.{info,warning,error} call as
    (level, msg) tuples, in call order, without emitting real log lines."""
    calls = []

    def _make(level):
        def record(msg, *args, **kwargs):
            calls.append((level, msg))
        return record

    monkeypatch.setattr(chat_module.logger, "info", _make("info"))
    monkeypatch.setattr(chat_module.logger, "warning", _make("warning"))
    monkeypatch.setattr(chat_module.logger, "error", _make("error"))
    return calls


def _kb_hit(score, chunk_id="doc-1", text="chunk text"):
    return {"id": chunk_id, "score": score, "text": text, "filename": "doc.pdf"}


def test_request_entry_logs_full_message_and_payload_and_auth_present_true(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "what is the refund policy?", "session_id": "sess-1", "top_k": 3},
        headers=JWT_HEADERS,
    )

    assert resp.status_code == 200
    level, first_msg = log_calls[0]
    assert level == "info"
    entry = json.loads(first_msg)
    assert entry["message"] == "what is the refund policy?"
    assert entry["session_id"] == "sess-1"
    assert entry["top_k"] == 3
    assert entry["category"] is None
    assert entry["service"] is None
    assert entry["subservice"] is None
    assert entry["payload"] is None
    assert entry["auth_present"] is True
    assert "request_id" in entry and entry["request_id"]


def test_request_entry_logs_auth_present_false_when_no_authorization(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    entry = json.loads(log_calls[0][1])
    assert entry["auth_present"] is False


def test_request_entry_logs_direct_taxonomy_routing_fields(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "is_valid_path", lambda category, service, subservice=None: True)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post(
        "/chat",
        json={
            "message": "balance please",
            "category": "account_info",
            "service": "balance",
            "payload": {"foo": "bar"},
        },
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    entry = json.loads(log_calls[0][1])
    assert entry["category"] == "account_info"
    assert entry["service"] == "balance"
    assert entry["payload"] == {"foo": "bar"}


def test_request_entry_never_logs_raw_jwt(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    raw_jwt = JWT_HEADERS["Authorization"].split(" ", 1)[1]
    for _level, msg in log_calls:
        assert raw_jwt not in msg
        assert JWT_HEADERS["Authorization"] not in msg


# --- KB path (_kb_stream) stage logging --------------------------------------


def test_kb_stream_logs_hit_count_and_top_score_on_success(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    hits = [_kb_hit(0.91), _kb_hit(0.5)]

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", lambda vector, top_k: hits)
    monkeypatch.setattr(chat_module, "stream_generate", _fake_stream_generate)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    hit_log = next(json.loads(msg) for level, msg in log_calls if "hit_count" in msg)
    assert hit_log["hit_count"] == 2
    assert hit_log["top_score"] == 0.91


def test_kb_stream_logs_top_score_none_on_zero_hits(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", lambda vector, top_k: [])
    monkeypatch.setattr(chat_module, "stream_generate", _fake_stream_generate)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    hit_log = next(json.loads(msg) for level, msg in log_calls if "hit_count" in msg)
    assert hit_log["hit_count"] == 0
    assert hit_log["top_score"] is None


def test_kb_stream_logs_full_answer_text_on_generation_success(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    answer_log = next(json.loads(msg) for level, msg in log_calls if '"answer"' in msg)
    assert answer_log["answer"] == "Hello world"


def test_kb_stream_logs_warning_on_embedding_http_status_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_embed_text_fails(message, client=None):
        request = httpx.Request("POST", "http://ollama/api/embed")
        response = httpx.Response(400, text="bad request", request=request)
        raise httpx.HTTPStatusError("bad", request=request, response=response)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", fake_embed_text_fails)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    level, msg = next((lvl, m) for lvl, m in log_calls if '"stage"' in m)
    assert level == "warning"
    entry = json.loads(msg)
    assert entry["stage"] == "embedding"
    assert "bad request" in entry["detail"]


def test_kb_stream_logs_warning_on_embedding_unreachable(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_embed_text_fails(message, client=None):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", "http://ollama/api/embed"))

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", fake_embed_text_fails)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    level, msg = next((lvl, m) for lvl, m in log_calls if '"stage"' in m)
    assert level == "warning"
    entry = json.loads(msg)
    assert entry["stage"] == "embedding"
    assert entry["detail"] == "Embedding model (Ollama) is unreachable"


def test_kb_stream_logs_error_on_vector_store_unreachable(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    def fake_search_fails(vector, top_k):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", fake_search_fails)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    level, msg = next((lvl, m) for lvl, m in log_calls if '"stage"' in m)
    assert level == "error"
    entry = json.loads(msg)
    assert entry["stage"] == "vector_search"
    assert entry["detail"] == "Vector store (Qdrant) is unreachable"


def test_kb_stream_logs_error_on_generation_failure_mid_stream(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_stream_generate_fails(prompt):
        yield "partial"
        raise httpx.ReadTimeout("boom", request=httpx.Request("POST", "http://ollama/api/generate"))

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", _fake_search)
    monkeypatch.setattr(chat_module, "stream_generate", fake_stream_generate_fails)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    level, msg = next((lvl, m) for lvl, m in log_calls if '"stage"' in m)
    assert level == "error"
    entry = json.loads(msg)
    assert entry["stage"] == "generation"
    assert entry["detail"] == "Generation model (Ollama) failed or became unreachable mid-stream"
    # Never logs a partial "answer" entry when generation blows up mid-stream.
    assert not any('"answer"' in m for _lvl, m in log_calls)


# --- banking-path per-branch logging ------------------------------------------


def test_clarification_logs_type_and_token(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return Clarification(question="Which account would you like to check?")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "check my thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    branch_log = next(json.loads(msg) for _lvl, msg in log_calls if '"type"' in msg)
    assert branch_log["type"] == "CLARIFICATION_REQUIRED"
    assert branch_log["token"] == "Which account would you like to check?"


def test_auth_required_logs_type_and_token(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    branch_log = next(json.loads(msg) for _lvl, msg in log_calls if '"type"' in msg)
    assert branch_log["type"] == "AUTH_REQUIRED"
    assert branch_log["token"] == "Please log in to continue with this request."


def test_banking_service_success_logs_type_token_and_unredacted_payload(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="transaction_history", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data=copy.deepcopy(_LEAKY_TXN_DATA))

    async def fake_post(self, url, *args, **kwargs):
        raise httpx.ConnectTimeout("boom")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "show my recent transactions"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    token_event = next(data for name, data in events if name == "token")

    branch_log = next(json.loads(msg) for _lvl, msg in log_calls if '"type"' in msg)
    assert branch_log["type"] == "BANKING_SERVICE"
    # The logged token matches whatever actually reached the customer.
    assert branch_log["token"] == token_event["token"]
    # The logged payload is the raw/unredacted result-event payload -- not
    # run through _redact_for_prompt (that redaction is spoken-reply-only).
    assert branch_log["payload"] == result_event["payload"]
    assert branch_log["payload"]["transactions"][0]["accountNumber"] == "9876543210"


# --- audit.log_banking_turn request_id correlation ----------------------------


def test_audit_log_banking_turn_request_id_honored_when_passed(monkeypatch):
    calls = []
    monkeypatch.setattr(audit_module.logger, "info", lambda msg, *a, **k: calls.append(msg))

    audit_module.log_banking_turn(
        None,
        {"type": "CLARIFICATION_REQUIRED", "category": None, "service": None, "subservice": None},
        request_id="fixed-request-id-123",
    )

    entry = json.loads(calls[0])
    assert entry["request_id"] == "fixed-request-id-123"


def test_audit_log_banking_turn_self_generates_request_id_when_omitted(monkeypatch):
    calls = []
    monkeypatch.setattr(audit_module.logger, "info", lambda msg, *a, **k: calls.append(msg))

    audit_module.log_banking_turn(
        None, {"type": "CLARIFICATION_REQUIRED", "category": None, "service": None, "subservice": None}
    )

    entry = json.loads(calls[0])
    assert isinstance(entry["request_id"], str)
    assert len(entry["request_id"]) == 32  # uuid4().hex


def test_audit_request_id_correlates_with_chat_requests_log_for_same_turn(client, monkeypatch):
    """End-to-end: the request_id chat.requests logs for a turn's entry log
    and branch log must match the request_id audit.log_banking_turn actually
    receives for that same turn, so the two logs can be joined."""

    async def fake_classify(message, recent_turns=None):
        return Clarification(question="Which account would you like to check?")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)
    log_calls = _install_chat_logger_spy(monkeypatch)

    audit_calls = []

    def fake_log_banking_turn(customer_identity, turn_classification, *, latency_ms=None, request_id=None):
        audit_calls.append(request_id)

    monkeypatch.setattr(chat_module.audit, "log_banking_turn", fake_log_banking_turn)

    resp = client.post("/chat", json={"message": "check my thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    entry_log = json.loads(log_calls[0][1])
    branch_log = next(json.loads(msg) for _lvl, msg in log_calls if '"type"' in msg)

    assert len(audit_calls) == 1
    assert audit_calls[0] == entry_log["request_id"] == branch_log["request_id"]
