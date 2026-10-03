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
    assert token_event["token"] == "This is placeholder information about transfer funds; the real service isn't connected to chat yet."

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
    assert "Tk 5.00" in token_event["token"]  # poisha -> taka (T-65)

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == {"balance": "500.00", "balanceFormatted": "৳5.00"}


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
    assert result_event["payload"] == {"balance": "500.00", "balanceFormatted": "৳5.00"}


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
    assert token_event["token"] == "This is placeholder information about transfer funds; the real service isn't connected to chat yet."

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
        "question": (
            "You have multiple accounts — which one did you mean? "
            "Savings account ending 111, Current account ending 222."
        ),
        # T-67: kept so the customer's next message can resume the original service.
        "candidates": _ACCOUNT_SELECTION_ACCOUNTS,
        "payload": {},
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


def test_kb_path_emits_kb_answer_result(client, monkeypatch):
    # T-52: the KB path now emits a "result" event (type "KB_ANSWER") after all
    # token events and before "done", same convention as every other branch.
    # _fake_search returns [] (ungrounded), so this covers the ungrounded shape.
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    event_names = [name for name, _ in events]

    assert event_names.count("token") == 2
    assert event_names[-2] == "result"
    assert event_names[-1] == "done"

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "KB_ANSWER"
    assert result_event["category"] is None
    assert result_event["service"] is None
    assert result_event["subservice"] is None
    assert result_event["routing"] is None
    assert result_event["payload"] == {"grounded": False, "hitCount": 0, "sources": None}


# --- KB path (_kb_stream) KB_ANSWER payload contract -- independent -----------
# --- coverage for TASKS.md T-52, written separately from the implementer's ---
# --- own 4 updated tests above: dedup-vs-raw-count, explicit None-vs-[] on ---
# --- sources, event ordering, and that the generation-failure branch still ---
# --- short-circuits before any result event is emitted. ----------------------


def test_kb_stream_result_grounded_dedupes_sources_but_hitcount_stays_raw(client, monkeypatch):
    # Two of three hits share a filename ("policy.pdf"). sources must dedupe
    # to one entry while preserving first-seen order (["policy.pdf", "faq.pdf"],
    # not ["faq.pdf", "policy.pdf"]), while hitCount must remain the raw hit
    # count (3), not the deduped source count (2).
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    hits = [
        {"id": "c1", "score": 0.9, "text": "t1", "filename": "policy.pdf"},
        {"id": "c2", "score": 0.8, "text": "t2", "filename": "faq.pdf"},
        {"id": "c3", "score": 0.7, "text": "t3", "filename": "policy.pdf"},
    ]

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", lambda vector, top_k: hits)
    monkeypatch.setattr(chat_module, "stream_generate", _fake_stream_generate)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["payload"]["grounded"] is True
    assert result_event["payload"]["hitCount"] == 3
    assert result_event["payload"]["sources"] == ["policy.pdf", "faq.pdf"]


def test_kb_stream_result_ungrounded_sources_is_none_not_empty_list(client, monkeypatch):
    # Must be `is None`, not merely falsy: an empty list would satisfy a loose
    # "no sources" check but is a different JSON shape (`[]` vs `null`) on the
    # wire, and frontend code may branch on which one it got.
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_kb_fakes(monkeypatch)  # _fake_search returns []
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["payload"]["grounded"] is False
    assert result_event["payload"]["hitCount"] == 0
    assert result_event["payload"]["sources"] is None


def test_kb_stream_result_event_ordering_grounded_and_ungrounded(client, monkeypatch):
    # In both the grounded and ungrounded case, "result" must be the
    # second-to-last SSE event, immediately followed by "done".
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "stream_generate", _fake_stream_generate)
    _install_session_fakes(monkeypatch)

    monkeypatch.setattr(chat_module, "search", lambda vector, top_k: [_kb_hit(0.9)])
    grounded_resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)
    grounded_names = [name for name, _ in _parse_sse(grounded_resp.text)]
    assert grounded_names[-2:] == ["result", "done"]

    monkeypatch.setattr(chat_module, "search", lambda vector, top_k: [])
    ungrounded_resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)
    ungrounded_names = [name for name, _ in _parse_sse(ungrounded_resp.text)]
    assert ungrounded_names[-2:] == ["result", "done"]


def test_kb_stream_generation_failure_never_emits_result_event(client, monkeypatch):
    # T-52 added a "result" event to the success path of _kb_stream, but the
    # pre-existing generation-failure branch (httpx.HTTPError mid-stream)
    # returns before reaching the grounded/sources computation -- it must
    # keep emitting only "error" (and never reach "done" either).
    async def fake_classify(message, recent_turns=None):
        return KbQuestion()

    async def fake_stream_generate_fails(prompt):
        yield "partial"
        raise httpx.ReadTimeout("boom")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(chat_module, "search", _fake_search)
    monkeypatch.setattr(chat_module, "stream_generate", fake_stream_generate_fails)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what is the refund policy?"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    event_names = [name for name, _ in _parse_sse(resp.text)]

    assert "result" not in event_names
    assert "done" not in event_names
    assert event_names[-1] == "error"


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


def test_audit_called_once_for_clarification_includes_question(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return Clarification(question="Which account would you like to check?")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_session_fakes(monkeypatch)
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": "check my thing"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy.calls) == 1
    args, kwargs = audit_spy.calls[0]
    _, turn_classification = args
    assert turn_classification["question"] == "Which account would you like to check?"


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
    assert result["balanceFormatted"] == "৳5.00"
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
    assert ledger["balanceFormatted"] == "৳25.00"

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
    assert txn["amountFormatted"] == "৳1.51"
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
    assert ledger["balanceFormatted"] == "৳25.00"


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
    assert payload["balanceFormatted"] == "৳5.00"


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
    assert txn["amountFormatted"] == "৳1.51"


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
    assert "cifNumber" not in result  # dropped, not placeholdered (live eval 2026-10-03)
    assert result["accountNumber"] == "••••••7890"


def test_redact_for_prompt_nid_always_redacted():
    data = {"nid": "1234567890123"}
    result = chat_module._redact_for_prompt(data)
    assert "nid" not in result


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
        return _FakeOllamaResponse({"response": "You spent Tk 1.51 on a transfer recently."})

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
    assert "••••••7890" in prompt or json.dumps("••••••7890")[1:-1] in prompt  # accountNumberMasked substitute, added by T-32 _enrich_payload
    assert "••••••7776" in prompt or json.dumps("••••••7776")[1:-1] in prompt  # masked description digit run

    # the result payload must be raw + masked/formatted, exactly as T-32 left it.
    result_event = next(data for name, data in events if name == "result")
    txn = result_event["payload"]["transactions"][0]
    assert txn["accountNumber"] == "1234567890"
    assert txn["accountNumberMasked"] == "••••••7890"
    assert txn["amountFormatted"] == "৳1.51"
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
    assert txn["amountFormatted"] == "৳1.00"


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


# --- payload-completeness guard (TASKS.md T-49): a fees/fee_quote --------
# --- BankingService result with an incomplete payload must get a --------
# --- deterministic CLARIFICATION_REQUIRED, and fulfill_banking_service ---
# --- must never be invoked -- previously this fell through to the -------
# --- adapter and surfaced as a generic SERVICE_UNAVAILABLE. --------------


def _never_call_fulfill(*args, **kwargs):
    raise AssertionError("fulfill_banking_service must not be called for an incomplete fees/fee_quote payload")


def test_missing_payload_fields_empty_for_unrelated_pair():
    assert chat_module._missing_payload_fields("account_info", "balance", None) == []
    assert chat_module._missing_payload_fields("account_info", "balance", {"anything": "x"}) == []


def test_missing_payload_fields_fees_fee_quote_none_payload_returns_both():
    assert chat_module._missing_payload_fields("fees", "fee_quote", None) == ["transactionType", "amount"]


def test_missing_payload_fields_fees_fee_quote_complete_payload_returns_empty():
    payload = {"transactionType": "bkash", "amount": 1000}
    assert chat_module._missing_payload_fields("fees", "fee_quote", payload) == []


def test_fee_quote_clarification_question_both_missing():
    question = chat_module._fee_quote_clarification_question(None)
    assert question == (
        "Sure — which transaction type would you like a fee quote for, and for what "
        "amount? For example, a bank transfer, bKash, or another wallet?"
    )


def test_fee_quote_clarification_question_amount_missing_names_transaction_type():
    question = chat_module._fee_quote_clarification_question({"transactionType": "other_bank"})
    assert question == (
        "Sure — how much would you like to send via other bank? I can give you "
        "the exact fee once I know the amount."
    )


def test_fee_quote_clarification_question_transaction_type_missing_mentions_formatted_amount():
    question = chat_module._fee_quote_clarification_question({"amount": 5000})
    assert question == (
        "Sure — you'd like a fee quote for ৳5,000. Which transaction type "
        "would you like that for? For example, a bank transfer, bKash, or another wallet?"
    )


def test_payload_clarification_question_unmapped_pair_uses_generic_fallback():
    question = chat_module._payload_clarification_question("account_info", "balance", None)
    assert question == "Could you share a few more details so I can help with that?"


def test_payload_clarification_question_fees_fee_quote_dispatch_byte_identical_with_and_without_subservice():
    """T-56 extended _payload_clarification_question's and
    _PAYLOAD_CLARIFICATION_BUILDERS' signatures to also pass a `subservice`
    argument through to every builder (needed by the new transfer builders).
    Confirms this signature change left fees/fee_quote's dispatch and output
    completely byte-identical to _fee_quote_clarification_question's own
    direct output -- both when subservice is omitted (its default, matching
    every pre-T-56 call site) and when some subservice value is explicitly
    passed through (fee_quote itself has no subservice in the real taxonomy,
    so the builder must simply ignore it rather than erroring or changing
    its wording)."""
    payload = {"transactionType": "other_bank"}
    expected = chat_module._fee_quote_clarification_question(payload)

    assert chat_module._payload_clarification_question("fees", "fee_quote", payload) == expected
    assert (
        chat_module._payload_clarification_question("fees", "fee_quote", payload, subservice=None)
        == expected
    )
    assert (
        chat_module._payload_clarification_question(
            "fees", "fee_quote", payload, subservice="some_subservice"
        )
        == expected
    )


def test_fees_fee_quote_payload_none_yields_clarification_without_calling_adapter(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="fees", service="fee_quote", subservice=None, payload=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what are your fees"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Sure — which transaction type would you like a fee quote for, and for what "
        "amount? For example, a bank transfer, bKash, or another wallet?"
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"
    assert result_event["category"] is None
    assert result_event["service"] is None
    assert result_event["subservice"] is None
    assert result_event["payload"] is None
    assert result_event["routing"] is None


def test_fees_fee_quote_payload_missing_amount_asks_for_amount_naming_transaction_type(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="fees", service="fee_quote", subservice=None, payload={"transactionType": "other_bank"}
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat", json={"message": "how much fees for sending to other bank accounts?"}, headers=JWT_HEADERS
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Sure — how much would you like to send via other bank? I can give you "
        "the exact fee once I know the amount."
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"


def test_fees_fee_quote_payload_missing_transaction_type_asks_which_type_mentioning_formatted_amount(
    client, monkeypatch
):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="fees", service="fee_quote", subservice=None, payload={"amount": 5000})

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "fee for sending 5000 taka"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Sure — you'd like a fee quote for ৳5,000. Which transaction type "
        "would you like that for? For example, a bank transfer, bKash, or another wallet?"
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"


def test_fees_fee_quote_complete_payload_calls_adapter_normally(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="fees",
            service="fee_quote",
            subservice=None,
            payload={"transactionType": "bkash", "amount": 1000},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    fulfill_calls = []
    mock_data = {"mock": True, "note": "synthetic fee quote"}

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((category, service, subservice, payload))
        return AdapterResult(data=mock_data)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat", json={"message": "how much does it cost to send money via bKash"}, headers=JWT_HEADERS
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == mock_data

    assert len(fulfill_calls) == 1
    assert fulfill_calls[0] == ("fees", "fee_quote", None, {"transactionType": "bkash", "amount": 1000})


def test_non_fees_service_balance_unaffected_by_payload_guard(client, monkeypatch):
    """Confirms no other (category, service) pair is caught by the guard --
    a normal account_info/balance request with no payload at all still
    proceeds straight to the adapter, with no clarification detour."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice=None, payload=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    fulfill_calls = []

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((category, service, subservice, payload))
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert len(fulfill_calls) == 1


# --- TRANSFER intent, response side only (TASKS.md T-56): transfer/bank_transfer -----
# --- and transfer/wallet_transfer extend the T-49 required-payload-fields guard, ----
# --- but once the payload is complete there is NO real adapter call at all (ADR-0008 /
# --- the standing GET-only policy -- a transfer is never executed from here) --------
# --- -- instead a deterministic BANKING_SERVICE confirmation summary is built and ---
# --- emitted directly. --------------------------------------------------------------


def test_missing_payload_fields_transfer_bank_transfer_none_payload_returns_both():
    assert chat_module._missing_payload_fields("transfer", "bank_transfer", None) == [
        "accountNumber",
        "amount",
    ]


def test_missing_payload_fields_transfer_bank_transfer_complete_payload_returns_empty():
    payload = {"accountNumber": "1234567890", "amount": 5000}
    assert chat_module._missing_payload_fields("transfer", "bank_transfer", payload) == []


def test_missing_payload_fields_transfer_wallet_transfer_none_payload_returns_both():
    assert chat_module._missing_payload_fields("transfer", "wallet_transfer", None) == [
        "walletNumber",
        "amount",
    ]


def test_missing_payload_fields_transfer_wallet_transfer_complete_payload_returns_empty():
    payload = {"walletNumber": "01812345678", "amount": 2000}
    assert chat_module._missing_payload_fields("transfer", "wallet_transfer", payload) == []


# --- clarification-question builders --------------------------------------------------


def test_bank_transfer_clarification_question_both_missing_names_subservice():
    question = chat_module._bank_transfer_clarification_question(None, "other_bank")
    assert question == (
        "Sure — which account number would you like to send money to via Other Bank "
        "Transfer, and how much?"
    )


def test_bank_transfer_clarification_question_amount_missing_names_account():
    question = chat_module._bank_transfer_clarification_question(
        {"accountNumber": "1234567890"}, "other_bank"
    )
    assert question == "Sure — how much would you like to send to account 1234567890?"


def test_bank_transfer_clarification_question_account_missing_mentions_formatted_amount():
    question = chat_module._bank_transfer_clarification_question({"amount": 5000}, "other_bank")
    assert question == "Sure — which account number would you like to send ৳5,000 to?"


def test_wallet_transfer_clarification_question_both_missing_names_provider():
    question = chat_module._wallet_transfer_clarification_question(None, "bkash")
    assert question == "Sure — to which bKash number would you like to send money, and how much?"


def test_wallet_transfer_clarification_question_amount_missing_names_wallet_number():
    question = chat_module._wallet_transfer_clarification_question(
        {"walletNumber": "01812345678"}, "bkash"
    )
    assert question == (
        "Sure — how much would you like to send to your bKash number 01812345678?"
    )


def test_wallet_transfer_clarification_question_wallet_number_missing_mentions_formatted_amount():
    question = chat_module._wallet_transfer_clarification_question({"amount": 5000}, "bkash")
    assert question == "Sure — which bKash number would you like to send ৳5,000 to?"


# --- full _chat_stream wiring: incomplete payload -> CLARIFICATION_REQUIRED, --------
# --- never touching fulfill_banking_service ------------------------------------------


def test_transfer_bank_transfer_missing_amount_asks_for_amount_naming_account(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="bank_transfer",
            subservice="other_bank",
            payload={"accountNumber": "1234567890"},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat", json={"message": "send money to account 1234567890"}, headers=JWT_HEADERS
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "Sure — how much would you like to send to account 1234567890?"

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"
    assert result_event["payload"] is None
    assert result_event["routing"] is None


def test_transfer_bank_transfer_missing_account_number_asks_for_account(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="bank_transfer",
            subservice="other_bank",
            payload={"amount": 5000},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "send 5000 to other bank"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == "Sure — which account number would you like to send ৳5,000 to?"

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"


def test_transfer_bank_transfer_missing_both_asks_for_both_naming_subservice(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer", service="bank_transfer", subservice="other_bank", payload=None
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "I want to send money"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Sure — which account number would you like to send money to via Other Bank "
        "Transfer, and how much?"
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"


def test_transfer_wallet_transfer_missing_amount_asks_for_amount(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="wallet_transfer",
            subservice="bkash",
            payload={"walletNumber": "01812345678"},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat", json={"message": "send to my bkash 01812345678"}, headers=JWT_HEADERS
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Sure — how much would you like to send to your bKash number 01812345678?"
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"


def test_transfer_wallet_transfer_missing_both_asks_for_both_naming_provider(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer", service="wallet_transfer", subservice="bkash", payload=None
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "send money via bkash"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Sure — to which bKash number would you like to send money, and how much?"
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"


# --- full _chat_stream wiring: complete payload -> deterministic BANKING_SERVICE -----
# --- confirmation summary, no adapter call at all ------------------------------------


def test_transfer_bank_transfer_complete_payload_builds_summary_without_calling_adapter(
    client, monkeypatch
):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="bank_transfer",
            subservice="other_bank",
            payload={"accountNumber": "1234567890", "amount": 5000},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "send 5000 to account 1234567890 via other bank"},
        headers=JWT_HEADERS,
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Here's your transfer summary: ৳5,000 to account 1234567890 via Other Bank "
        "Transfer. I can't complete this for you here — please confirm and finish it "
        "in the app."
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["category"] == "transfer"
    assert result_event["service"] == "bank_transfer"
    assert result_event["subservice"] == "other_bank"
    assert result_event["payload"] == {
        "accountNumber": "1234567890",
        "amount": 5000,
        "formattedAmount": "৳5,000",
        "executed": False,
    }
    assert result_event["routing"] == {
        "category": "transfer",
        "service": "bank_transfer",
        "subservice": "other_bank",
        "action": "other_bank_transfer",
    }

    assert len(record_turn_spy.calls) == 1
    recorded_turn = record_turn_spy.calls[0][0][1]
    assert recorded_turn.classification == {
        "type": "BANKING_SERVICE",
        "category": "transfer",
        "service": "bank_transfer",
        "subservice": "other_bank",
    }


def test_transfer_wallet_transfer_complete_payload_builds_summary_without_calling_adapter(
    client, monkeypatch
):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="wallet_transfer",
            subservice="bkash",
            payload={"walletNumber": "01812345678", "amount": 2000},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat", json={"message": "send 2000 to my bkash 01812345678"}, headers=JWT_HEADERS
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"] == (
        "Here's your transfer summary: ৳2,000 to your bKash number 01812345678. I "
        "can't complete this for you here — please confirm and finish it in the app."
    )

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == {
        "walletNumber": "01812345678",
        "amount": 2000,
        "formattedAmount": "৳2,000",
        "executed": False,
    }
    assert result_event["routing"] == {
        "category": "transfer",
        "service": "wallet_transfer",
        "subservice": "bkash",
        "action": "bkash_transfer",
    }


def test_transfer_direct_route_complete_payload_bypasses_classification(client, monkeypatch):
    """Per T-56's verification instructions: the direct category/service/subservice/
    payload route (ChatRequest fields, bypassing classify() entirely) must also hit the
    no-adapter summary branch -- useful for live-verifying this behavior before
    conversation-routing's part 1 (classify() extraction) has landed."""

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "is_valid_path", lambda category, service, subservice=None: True)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={
            "message": "send money",
            "category": "transfer",
            "service": "bank_transfer",
            "subservice": "other_bank",
            "payload": {"accountNumber": "1234567890", "amount": 5000},
        },
        headers=JWT_HEADERS,
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"]["executed"] is False
    assert result_event["routing"]["action"] == "other_bank_transfer"


def test_transfer_without_identity_still_requires_auth_before_summary(client, monkeypatch):
    """The existing AUTH_REQUIRED gate (no customer_identity) must still take
    precedence over the new no-adapter transfer branch -- a transfer summary is never
    built for an unauthenticated request."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="bank_transfer",
            subservice="other_bank",
            payload={"accountNumber": "1234567890", "amount": 5000},
        )

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "send money"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "AUTH_REQUIRED"


def test_transfer_summary_turn_recorded_as_banking_service_not_clarification_required(client, monkeypatch):
    """TASKS.md T-56 focus: the no-adapter transfer branch's recorded turn
    must have classification["type"] == "BANKING_SERVICE" (not
    "CLARIFICATION_REQUIRED") -- otherwise a later, unrelated follow-up
    message could be mistaken by _try_deterministic_payload_completion for a
    still-pending T-49 payload-completeness guard reply and get its bare
    number merged into an already-finished transfer payload instead of being
    treated as a fresh request."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="bank_transfer",
            subservice="other_bank",
            payload={"accountNumber": "1234567890", "amount": 5000},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)
    record_turn_spy = _install_session_fakes(monkeypatch)

    resp = client.post(
        "/chat",
        json={"message": "send 5000 to account 1234567890 via other bank"},
        headers=JWT_HEADERS,
    )

    assert resp.status_code == 200
    assert len(record_turn_spy.calls) == 1
    recorded_turn = record_turn_spy.calls[0][0][1]
    assert recorded_turn.classification["type"] == "BANKING_SERVICE"

    # The recorded turn must never be treated as a pending T-49 guard by a
    # later message -- confirms _try_deterministic_payload_completion falls
    # through (returns None) for it, exactly like any other non-clarification
    # recorded turn.
    assert chat_module._try_deterministic_payload_completion([recorded_turn], "2000") is None
    assert chat_module._try_deterministic_payload_completion([recorded_turn], "ok thanks") is None


def test_transfer_summary_followed_by_unrelated_message_classifies_fresh_and_still_records(
    client, monkeypatch
):
    """Full round trip for the same concern as above, driven through two real
    /chat calls: after a transfer summary is recorded, a second, unrelated
    message must still call classify() fresh (never silently "completed"
    against the already-finished transfer payload) and must still reach
    record_turn for that second turn too -- confirming the new transfer
    branch doesn't accidentally break session/recording wiring for whatever
    comes after it."""

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_classify_transfer(message, recent_turns=None):
        return BankingService(
            category="transfer",
            service="bank_transfer",
            subservice="other_bank",
            payload={"accountNumber": "1234567890", "amount": 5000},
        )

    recorded_turns = []

    def fake_record_turn(customer_id, turn):
        recorded_turns.append(turn)

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake_classify_transfer)
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])
    monkeypatch.setattr(chat_module, "record_turn", fake_record_turn)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)

    resp = client.post(
        "/chat",
        json={"message": "send 5000 to account 1234567890 via other bank"},
        headers=JWT_HEADERS,
    )

    assert resp.status_code == 200
    result_event = next(data for name, data in _parse_sse(resp.text) if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert len(recorded_turns) == 1
    first_turn = recorded_turns[0]
    assert first_turn.classification["type"] == "BANKING_SERVICE"

    # Second call: session now returns the just-recorded transfer turn as
    # recent_turns. A fresh, unrelated balance request must call classify()
    # (receiving that turn as context, unused), not be swallowed by the
    # deterministic bare-amount-completion shortcut, and must proceed to a
    # real adapter call + a second record_turn as normal.
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [first_turn])

    classify_calls = []

    async def fake_classify_balance(message, recent_turns=None):
        classify_calls.append((message, recent_turns))
        return BankingService(category="account_info", service="balance", subservice="balance")

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "classify", fake_classify_balance)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)

    resp2 = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp2.status_code == 200
    result_event2 = next(data for name, data in _parse_sse(resp2.text) if name == "result")
    assert result_event2["type"] == "BANKING_SERVICE"

    assert len(classify_calls) == 1
    assert classify_calls[0] == ("what's my balance", [first_turn])
    assert len(recorded_turns) == 2
    assert recorded_turns[1].classification["type"] == "BANKING_SERVICE"
    assert recorded_turns[1].classification["category"] == "account_info"


def test_fees_fee_quote_still_calls_real_adapter_unaffected_by_transfer_branch(client, monkeypatch):
    """Confirms the new transfer-only no-adapter branch is scoped exactly to
    (transfer, bank_transfer)/(transfer, wallet_transfer) -- fees/fee_quote (and every
    other existing real service) still calls fulfill_banking_service exactly as
    before."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="fees",
            service="fee_quote",
            subservice=None,
            payload={"transactionType": "bkash", "amount": 1000},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    fulfill_calls = []

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((category, service, subservice, payload))
        return AdapterResult(data={"mock": True})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "fee for bkash 1000"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(fulfill_calls) == 1


# --- deterministic bare-amount completion of a pending T-49 payload ----------
# --- guard (TASKS.md T-55): _extract_single_amount, --------------------------
# --- _DETERMINISTIC_FIELD_EXTRACTORS, _try_deterministic_payload_completion, -
# --- and their wiring into _chat_stream's implicit-classification path -------
# --- (bypassing classify() when -- and only when -- the last turn was -------
# --- specifically T-49's known-category/service guard, not a genuine --------
# --- ambiguous Clarification). ------------------------------------------------


# --- _extract_single_amount ---------------------------------------------------


def test_extract_single_amount_plain_number():
    assert chat_module._extract_single_amount("2000") == 2000


def test_extract_single_amount_ignores_trailing_unit_word():
    assert chat_module._extract_single_amount("2000 taka") == 2000
    assert chat_module._extract_single_amount("5000 tk") == 5000


def test_extract_single_amount_comma_separated_thousands():
    assert chat_module._extract_single_amount("5,000") == 5000
    assert chat_module._extract_single_amount("5,000 tk") == 5000


def test_extract_single_amount_decimal():
    assert chat_module._extract_single_amount("2000.50") == 2000.5


def test_extract_single_amount_zero_numeric_substrings_returns_none():
    assert chat_module._extract_single_amount("hello") is None


def test_extract_single_amount_multiple_numeric_substrings_returns_none():
    assert chat_module._extract_single_amount("2000 or 3000") is None


# --- _try_deterministic_payload_completion ------------------------------------


def _deterministic_guard_turn(**classification_overrides):
    """A ChatTurn shaped like the T-49 guard's stored turn_classification: a
    CLARIFICATION_REQUIRED with known, non-null category/service/missingFields
    (as opposed to a genuine ambiguous Clarification, which stores
    category=None/service=None)."""
    classification = {
        "type": "CLARIFICATION_REQUIRED",
        "category": "fees",
        "service": "fee_quote",
        "subservice": None,
        "payload": {"transactionType": "bkash"},
        "question": "Sure — how much would you like to send via bkash?",
        "missingFields": ["amount"],
    }
    classification.update(classification_overrides)
    return chat_module.ChatTurn(
        timestamp=datetime.now(timezone.utc),
        message="send via bkash",
        classification=classification,
    )


def test_try_deterministic_payload_completion_resolves_amount_from_bare_reply():
    result = chat_module._try_deterministic_payload_completion([_deterministic_guard_turn()], "2000")
    assert result == BankingService(
        category="fees",
        service="fee_quote",
        subservice=None,
        payload={"transactionType": "bkash", "amount": 2000},
    )


def test_try_deterministic_payload_completion_none_for_genuine_ambiguous_clarification():
    ambiguous_turn = chat_module.ChatTurn(
        timestamp=datetime.now(timezone.utc),
        message="check my thing",
        classification={
            "type": "CLARIFICATION_REQUIRED",
            "category": None,
            "service": None,
            "subservice": None,
            "question": "Which account would you like to check?",
        },
    )
    assert chat_module._try_deterministic_payload_completion([ambiguous_turn], "2000") is None
    assert chat_module._try_deterministic_payload_completion([ambiguous_turn], "anything at all") is None


def test_try_deterministic_payload_completion_none_when_missing_field_has_no_extractor():
    turn = _deterministic_guard_turn(missingFields=["transactionType"], payload={"amount": 5000})
    assert chat_module._try_deterministic_payload_completion([turn], "bkash") is None


def test_try_deterministic_payload_completion_none_when_message_has_no_extractable_number():
    turn = _deterministic_guard_turn()
    assert chat_module._try_deterministic_payload_completion([turn], "not sure") is None
    assert chat_module._try_deterministic_payload_completion([turn], "2000 or 3000") is None


def test_try_deterministic_payload_completion_none_when_last_turn_not_clarification_required():
    turn = chat_module.ChatTurn(
        timestamp=datetime.now(timezone.utc),
        message="what's my balance",
        classification={"type": "BANKING_SERVICE", "category": "account_info", "service": "balance"},
    )
    assert chat_module._try_deterministic_payload_completion([turn], "2000") is None


def test_try_deterministic_payload_completion_none_for_empty_recent_turns():
    assert chat_module._try_deterministic_payload_completion([], "2000") is None


# --- full /chat SSE flow: deterministic completion wired into _chat_stream ---


def test_chat_stream_bare_amount_reply_bypasses_classify_and_completes_payload(client, monkeypatch):
    """First call: an incomplete fees/fee_quote BankingService (as classify()
    would return) trips the T-49 guard and asks for the amount; its
    turn_classification (with missingFields) is what record_turn stores.
    Second call: a bare-amount reply, with that stored turn now returned by
    get_classification_context, must resolve deterministically -- classify()
    must not be called again -- and the merged, now-complete payload must
    reach fulfill_banking_service directly."""

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        return BankingService(
            category="fees", service="fee_quote", subservice=None, payload={"transactionType": "bkash"}
        )

    recorded_turns = []

    def fake_record_turn(customer_id, turn):
        recorded_turns.append(turn)

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])
    monkeypatch.setattr(chat_module, "record_turn", fake_record_turn)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", _never_call_fulfill)

    resp = client.post("/chat", json={"message": "how much to send via bkash"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    result_event = next(data for name, data in _parse_sse(resp.text) if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"
    assert len(classify_calls) == 1
    assert len(recorded_turns) == 1

    first_turn = recorded_turns[0]
    assert first_turn.classification["missingFields"] == ["amount"]
    assert first_turn.classification["category"] == "fees"
    assert first_turn.classification["service"] == "fee_quote"

    # Second call: bare-amount reply, session now returns the stored guard turn.
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [first_turn])

    fulfill_calls = []
    mock_data = {"mock": True, "note": "synthetic fee quote"}

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((category, service, subservice, payload))
        return AdapterResult(data=mock_data)

    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)

    resp2 = client.post("/chat", json={"message": "2000"}, headers=JWT_HEADERS)

    assert resp2.status_code == 200
    result_event2 = next(data for name, data in _parse_sse(resp2.text) if name == "result")
    assert result_event2["type"] == "BANKING_SERVICE"
    assert result_event2["payload"] == mock_data

    # classify() was never called for the second turn -- the deterministic
    # path resolved it entirely on its own.
    assert len(classify_calls) == 1
    assert len(fulfill_calls) == 1
    assert fulfill_calls[0] == ("fees", "fee_quote", None, {"transactionType": "bkash", "amount": 2000})


def test_chat_stream_unparseable_amount_reply_falls_through_to_classify(client, monkeypatch):
    """A reply that doesn't unambiguously supply the missing amount (no
    numbers at all here) must not be guessed at -- it falls through to a
    normal, fresh classify() call, exactly as if no guard were pending."""

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        return BankingService(category="account_info", service="balance", subservice=None, payload=None)

    stored_turn = _deterministic_guard_turn()

    fulfill_calls = []

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((category, service, subservice, payload))
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [stored_turn])
    monkeypatch.setattr(chat_module, "record_turn", _spy())
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)

    resp = client.post("/chat", json={"message": "not sure"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    result_event = next(data for name, data in _parse_sse(resp.text) if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"

    assert classify_calls == ["not sure"]
    assert len(fulfill_calls) == 1


def test_chat_stream_genuine_ambiguous_clarification_never_uses_deterministic_path(client, monkeypatch):
    """A genuinely ambiguous prior Clarification (category=None/service=None)
    must always be resolved via classify(), regardless of what the follow-up
    message looks like -- even a bare number, which would otherwise look
    exactly like a valid deterministic-completion reply."""

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        return Clarification(question="Which account would you like to check?")

    stored_turn = chat_module.ChatTurn(
        timestamp=datetime.now(timezone.utc),
        message="check my thing",
        classification={
            "type": "CLARIFICATION_REQUIRED",
            "category": None,
            "service": None,
            "subservice": None,
            "question": "Which account would you like to check?",
        },
    )

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [stored_turn])
    monkeypatch.setattr(chat_module, "record_turn", _spy())

    resp = client.post("/chat", json={"message": "2000"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert classify_calls == ["2000"]
