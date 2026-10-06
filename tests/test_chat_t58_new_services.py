"""Independent chat.py-level coverage for TASKS.md T-58 (ACCOUNT_INFO's "my
loans"/FD-profit/DPS-profit and ATM_SUPPORT's "list disputes" read-only
endpoints).

The implementing agents already wrote ~25 adapter-unit tests in
tests/test_real_adapters.py (bare-array wrapping, 0/1/2+-match ledger-account
resolution, auth errors, empty-list success). This file deliberately does NOT
duplicate those -- it covers the same behaviors one level up, at the full
/chat SSE-stream contract, where app/routes/chat.py's generic exception
handlers and success-path code (data.get(...), _account_selection_reply,
etc.) actually consume the adapters' output. Specifically:

  1. The bare-array-wrapping fix for LoansAdapter, exercised through the REAL
     adapter chain (fulfill_banking_service is NOT mocked here) so the fix is
     proven at the exact point the AttributeError crash was observed, not
     just at the adapter-unit level.
  2. Whether AdapterAccountSelectionRequiredError's except-clause in
     app/routes/chat.py -- written against _resolve_account_number's
     accountNumber/accountType-shaped trimmed accounts -- actually
     generalizes to _resolve_ledger_account_identifier's
     identifier/chartOfAccountName-shaped trimmed accounts (new in T-58,
     used by Fd/DpsProfitHistoryAdapter).
  3. The 0-match case (AdapterUnavailableError) reaching a clean
     SERVICE_UNAVAILABLE result.
  4. The AUTH_REQUIRED gate (both the no-identity and the adapter-auth-error
     paths) generalizing to the new service_requests/disputes category, not
     just account_info-shaped ones.

Follows tests/test_chat_banking_flow.py's conventions: classify/verify_jwt/
fulfill_banking_service (or, for test 1, the lower-level httpx call site used
by app/banking/adapters/real.py's _call()) are monkeypatched; nothing here
touches a live Ollama, the taxonomy cache, or the real in-memory session
store.
"""
import json

import httpx
import pytest

import app.routes.chat as chat_module
from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterResult,
    AdapterUnavailableError,
)
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService

from tests.conftest import AUTH_HEADERS

CUSTOMER_ID = "cust-123"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


def _install_session_fakes(monkeypatch):
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])
    monkeypatch.setattr(chat_module, "record_turn", lambda *a, **k: None)


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


class _FakeHttpResponse:
    """Minimal httpx.Response stand-in for the platform API, matching
    tests/test_real_adapters.py's FakeResponse shape (is_success/json/text)
    -- that file monkeypatches httpx.AsyncClient.request the same way."""

    def __init__(self, status_code=200, json_data=None, text="error"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


def _install_platform_request(monkeypatch, response):
    """Patches httpx.AsyncClient.request -- the call site used by
    app/banking/adapters/real.py's shared _call() helper -- so a test can
    drive a REAL adapter (not a mocked fulfill_banking_service) all the way
    from /chat through adapter_map.get_adapter_name and the real adapter's
    fulfill(), without ever hitting a live platform API."""

    async def fake_request(self, method, path, *, headers=None, params=None, json=None):
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)


# --- 1. LoansAdapter bare-array-wrapping fix, exercised end-to-end ----------


def test_loans_adapter_bare_array_response_end_to_end_no_crash(client, monkeypatch):
    """T-58 regression: GET /loan/v1/loans was live-confirmed to return a
    bare JSON array. Before LoansAdapter wrapped it under {"loans": [...]},
    this reached app/routes/chat.py's success branch's `data.get("mock")`
    check on a bare list and crashed with
    `AttributeError: 'list' object has no attribute 'get'`. This drives the
    REAL LoansAdapter (fulfill_banking_service is left unmocked, routed
    through the real adapter_map) through the full /chat SSE stream, proving
    the fix holds at the exact point the crash was observed -- not just at
    the adapter-unit level, where test_real_adapters.py already covers the
    wrapping itself in isolation."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="loan_services", service="my_loans", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_synthesize_reply(message, service, subservice, data):
        return "Here is your loan information."

    bare_array_body = [
        {"id": "loan-1", "status": "ACTIVE"},
        {"id": "loan-2", "status": "CLOSED"},
    ]
    _install_platform_request(monkeypatch, _FakeHttpResponse(json_data=bare_array_body))

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "_synthesize_reply", fake_synthesize_reply)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my loans"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["category"] == "loan_services"
    assert result_event["service"] == "my_loans"
    assert result_event["payload"] == {"loans": bare_array_body}


# --- 2. AdapterAccountSelectionRequiredError generalization to ledger-shaped -
# --- accounts (FD/DPS) -------------------------------------------------------


_LEDGER_ACCOUNT_SELECTION_CANDIDATES = [
    {"identifier": "FD-1", "chartOfAccountName": "Fixed Deposit"},
    {"identifier": "FD-2", "chartOfAccountName": "Fixed Deposit"},
]


def test_fd_profit_history_two_matches_yields_account_selection_required(client, monkeypatch):
    """Confirms the except AdapterAccountSelectionRequiredError clause in
    app/routes/chat.py IS a generic, shared handler: it fires correctly
    (right event type, right trimmed payload passed through verbatim) for
    _resolve_ledger_account_identifier's identifier/chartOfAccountName-shaped
    accounts, not just _resolve_account_number's original
    accountNumber/accountType shape.

    _account_selection_reply() (via _describe_selection_account()) branches
    on which fields are present: a ledger-account dict has neither
    accountType nor accountNumber, so it's described from
    chartOfAccountName + the last 6 characters of identifier instead --
    producing two visibly distinct options rather than both collapsing to
    the same blank-filled string.
    """

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="fd_profit_history", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterAccountSelectionRequiredError(_LEDGER_ACCOUNT_SELECTION_CANDIDATES)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my FD profit history"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "ACCOUNT_SELECTION_REQUIRED"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == "fd_profit_history"
    # the event type + the raw trimmed list both generalize correctly --
    # exc.accounts is passed through verbatim regardless of its shape
    assert result_event["payload"] == {"accounts": _LEDGER_ACCOUNT_SELECTION_CANDIDATES}

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("choose:")
    assert "Fixed Deposit ending FD-1" in token_event["token"]
    assert "Fixed Deposit ending FD-2" in token_event["token"]


# --- 3. Zero-match FD/DPS -> clean SERVICE_UNAVAILABLE ----------------------


@pytest.mark.parametrize(
    "service,not_found_message",
    [
        ("fd_profit_history", "No Fixed Deposit account found"),
        ("dps_profit_history", "No DPS account found"),
    ],
)
def test_profit_history_zero_matches_yields_service_unavailable(
    client, monkeypatch, service, not_found_message
):
    """FdProfitHistoryAdapter/DpsProfitHistoryAdapter raise
    AdapterUnavailableError(not_found_message) when the customer has no
    FD/DPS account at all (0 matches). Confirms this reaches a clean,
    generic SERVICE_UNAVAILABLE /chat result -- not a crash, and not leaking
    the adapter's internal reason string into the customer-facing token --
    at the full /chat response level, not just as an adapter-unit
    pytest.raises check."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service=service, subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterUnavailableError(not_found_message)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my profit history"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("unavailable:")
    # the adapter's specific reason must never leak into the customer-facing token
    assert not_found_message not in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "SERVICE_UNAVAILABLE"
    assert result_event["category"] == "account_info"
    assert result_event["service"] == service


# --- 4. AUTH_REQUIRED gate generalizes to service_requests/disputes --------


def test_disputes_without_identity_requires_auth(client, monkeypatch):
    """Confirms the AUTH_REQUIRED gate for a missing customer_identity isn't
    implicitly scoped to account_info-shaped services -- it fires the same
    way for the new service_requests/disputes category, and never calls the
    adapter at all."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="service_requests", service="disputes", subservice=None)

    fulfill_calls = []

    async def fake_fulfill(*args, **kwargs):
        fulfill_calls.append((args, kwargs))
        return AdapterResult(data={})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my disputes"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("login_needed:")

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "AUTH_REQUIRED"
    assert result_event["category"] == "service_requests"
    assert result_event["service"] == "disputes"

    assert fulfill_calls == []


def test_disputes_adapter_auth_error_requires_auth(client, monkeypatch):
    """Same AUTH_REQUIRED generalization check, but for the adapter-level
    401/403 path (AdapterAuthError raised by DisputesAdapter after a
    customer_identity WAS resolved)."""

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="service_requests", service="disputes", subservice=None)

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterAuthError

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "show my disputes"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "AUTH_REQUIRED"
    assert result_event["category"] == "service_requests"
    assert result_event["service"] == "disputes"
