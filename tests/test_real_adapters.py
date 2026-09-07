"""Tests for app/banking/adapters/real.py: the 5 real adapters (balance,
transaction_history, accounts, device_history, login_history) that call the
platform API via a shared _call() helper.

httpx.AsyncClient.request is monkeypatched directly (matching
tests/test_taxonomy.py's style of monkeypatching the async call site rather
than pulling in a new test dependency like respx). No test hits the real
platform API -- the implementer already verified live manually per the task
instructions.

fulfill() is async; following tests/test_adapter_base.py's pattern, we drive
it with asyncio.run() inside sync test functions rather than adding
pytest-asyncio as a dependency.
"""
import asyncio

import httpx
import pytest

import app.banking.adapters.real as real
from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterResult,
    AdapterUnavailableError,
)
from app.banking.identity import CustomerIdentity

_IDENTITY = CustomerIdentity(customer_id="cust-123")
_JWT = "test.jwt.token"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="error"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


def _install_request(monkeypatch, response=None, exception=None):
    """Patches httpx.AsyncClient.request. Returns the list of captured calls
    (each a dict of method/path/headers/params/json) for later assertions."""
    calls = []

    async def fake_request(self, method, path, *, headers=None, params=None, json=None):
        calls.append(
            {"method": method, "path": path, "headers": headers, "params": params, "json": json}
        )
        if exception is not None:
            raise exception
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    return calls


# (attribute name on the real module, a payload that satisfies that
# adapter's required fields) -- used to drive every adapter through a
# generic HTTP-error scenario without needing adapter-specific payloads.
_ADAPTERS_WITH_VALID_PAYLOAD = [
    ("balance_adapter", {"accountNumber": "111"}),
    ("transaction_history_adapter", {"accountNumber": "111"}),
    ("accounts_adapter", {}),
    ("device_history_adapter", {}),
    ("login_history_adapter", {"deviceId": "dev-1"}),
]


@pytest.mark.parametrize("attr_name,payload", _ADAPTERS_WITH_VALID_PAYLOAD)
def test_401_raises_adapter_auth_error(monkeypatch, attr_name, payload):
    _install_request(monkeypatch, response=FakeResponse(status_code=401))
    adapter = getattr(real, attr_name)

    with pytest.raises(AdapterAuthError):
        asyncio.run(adapter.fulfill(_IDENTITY, _JWT, "subservice", payload))


@pytest.mark.parametrize("attr_name,payload", _ADAPTERS_WITH_VALID_PAYLOAD)
def test_403_raises_adapter_auth_error(monkeypatch, attr_name, payload):
    _install_request(monkeypatch, response=FakeResponse(status_code=403))
    adapter = getattr(real, attr_name)

    with pytest.raises(AdapterAuthError):
        asyncio.run(adapter.fulfill(_IDENTITY, _JWT, "subservice", payload))


@pytest.mark.parametrize("attr_name,payload", _ADAPTERS_WITH_VALID_PAYLOAD)
def test_500_raises_adapter_unavailable_error(monkeypatch, attr_name, payload):
    _install_request(monkeypatch, response=FakeResponse(status_code=500))
    adapter = getattr(real, attr_name)

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(adapter.fulfill(_IDENTITY, _JWT, "subservice", payload))


@pytest.mark.parametrize("attr_name,payload", _ADAPTERS_WITH_VALID_PAYLOAD)
def test_httpx_error_during_request_raises_adapter_unavailable_error_not_raw_httpx(
    monkeypatch, attr_name, payload
):
    _install_request(monkeypatch, exception=httpx.ConnectError("connection refused"))
    adapter = getattr(real, attr_name)

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(adapter.fulfill(_IDENTITY, _JWT, "subservice", payload))


def test_balance_adapter_parses_nested_data_shape(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(json_data={"data": {"balance": "100.00"}}))

    result = asyncio.run(
        real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {"accountNumber": "111"})
    )

    assert result == AdapterResult(data={"balance": "100.00"})


def test_balance_adapter_parses_bare_field_fallback_shape(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(json_data={"balance": "100.00"}))

    result = asyncio.run(
        real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {"accountNumber": "111"})
    )

    assert result == AdapterResult(data={"balance": "100.00"})


def test_transaction_history_adapter_returns_whole_body_on_success(monkeypatch):
    body = {"data": {"transactions": [{"id": "tx-1"}]}}
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history", {"accountNumber": "111"}
        )
    )

    assert result == AdapterResult(data=body)


def test_accounts_adapter_returns_whole_body_on_success(monkeypatch):
    body = {"data": {"accounts": []}}
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.accounts_adapter.fulfill(_IDENTITY, _JWT, "accounts", {}))

    assert result == AdapterResult(data=body)


def test_accounts_adapter_with_id_calls_detail_path(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"data": {}}))

    asyncio.run(real.accounts_adapter.fulfill(_IDENTITY, _JWT, "accounts", {"id": "acc-123"}))

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/polygon-bank/v1/accounts/acc-123"


def test_accounts_adapter_without_id_calls_list_path(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"data": {}}))

    asyncio.run(real.accounts_adapter.fulfill(_IDENTITY, _JWT, "accounts", {}))

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"


def test_device_history_adapter_wraps_bare_array_response_under_devices_key(monkeypatch):
    """T-22 regression test: GET /auth/v1/devices returns a bare JSON array
    (not an object), and the raw list must never flow through unwrapped --
    app/routes/chat.py's success-path calls data.get("mock") on the adapter
    result, which crashes with AttributeError on a bare list. fulfill() must
    wrap the array under a "devices" key so callers always get a dict."""
    body = [
        {"id": 1, "deviceName": "iPhone"},
        {"id": 2, "deviceName": "Pixel"},
    ]
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.device_history_adapter.fulfill(_IDENTITY, _JWT, "device_history", None))

    assert result == AdapterResult(data={"devices": body})
    assert isinstance(result.data, dict)


def test_login_history_adapter_returns_whole_body_on_success(monkeypatch):
    body = {"data": {"logins": []}}
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.login_history_adapter.fulfill(
            _IDENTITY, _JWT, "login_history", {"deviceId": "dev-1"}
        )
    )

    assert result == AdapterResult(data=body)


def test_login_history_adapter_missing_device_id_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.login_history_adapter.fulfill(_IDENTITY, _JWT, "login_history", {}))

    assert calls == []


def _install_path_responses(monkeypatch, responses_by_path):
    """Like _install_request, but for scenarios where a single fulfill() call
    issues more than one HTTP request (T-21's implicit accounts lookup via
    _resolve_account_number, followed by the balance/transaction-list call
    itself) -- routes each fake response by exact request path so the two
    calls can return different bodies."""
    calls = []

    async def fake_request(self, method, path, *, headers=None, params=None, json=None):
        calls.append(
            {"method": method, "path": path, "headers": headers, "params": params, "json": json}
        )
        return responses_by_path[path]

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    return calls


# --- T-21: _resolve_account_number (implicit account resolution) ------------


def test_balance_adapter_explicit_account_number_skips_accounts_lookup(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"data": {"balance": "250.00"}}))

    result = asyncio.run(
        real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {"accountNumber": "111"})
    )

    assert len(calls) == 1
    assert calls[0]["path"] == "/transfer/v1/accounting/balance"
    assert result == AdapterResult(data={"balance": "250.00"})


def test_transaction_history_adapter_explicit_account_number_skips_accounts_lookup(monkeypatch):
    body = {"data": {"transactions": []}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history", {"accountNumber": "111"}
        )
    )

    assert len(calls) == 1
    assert calls[0]["path"] == "/transfer/v1/accounting/transaction-list"
    assert result == AdapterResult(data=body)


def test_balance_adapter_zero_accounts_raises_adapter_unavailable(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"data": {"accounts": []}}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {}))

    assert len(calls) == 1
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"


def test_transaction_history_adapter_zero_accounts_raises_adapter_unavailable(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"data": {"accounts": []}}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.transaction_history_adapter.fulfill(_IDENTITY, _JWT, "transaction_history", {}))

    assert len(calls) == 1
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"


def test_balance_adapter_single_account_auto_resolves_transparently(monkeypatch):
    accounts_body = {
        "data": {
            "accounts": [
                {"accountNumber": "999", "accountName": "Primary", "accountType": "SAVINGS", "balance": "10.00"}
            ]
        }
    }
    balance_body = {"data": {"balance": "10.00"}}
    calls = _install_path_responses(
        monkeypatch,
        {
            "/polygon-bank/v1/accounts": FakeResponse(json_data=accounts_body),
            "/transfer/v1/accounting/balance": FakeResponse(json_data=balance_body),
        },
    )

    result = asyncio.run(real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {}))

    assert result == AdapterResult(data={"balance": "10.00"})
    assert len(calls) == 2
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"
    assert calls[1]["path"] == "/transfer/v1/accounting/balance"
    assert calls[1]["json"] == {"accountNumber": "999"}


def test_transaction_history_adapter_single_account_auto_resolves_transparently(monkeypatch):
    accounts_body = {
        "data": {
            "accounts": [
                {"accountNumber": "999", "accountName": "Primary", "accountType": "SAVINGS", "balance": "10.00"}
            ]
        }
    }
    transactions_body = {"data": {"transactions": [{"id": "tx-1"}]}}
    calls = _install_path_responses(
        monkeypatch,
        {
            "/polygon-bank/v1/accounts": FakeResponse(json_data=accounts_body),
            "/transfer/v1/accounting/transaction-list": FakeResponse(json_data=transactions_body),
        },
    )

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(_IDENTITY, _JWT, "transaction_history", {})
    )

    assert result == AdapterResult(data=transactions_body)
    assert len(calls) == 2
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"
    assert calls[1]["path"] == "/transfer/v1/accounting/transaction-list"
    assert calls[1]["params"]["accountNumber"] == "999"


def test_balance_adapter_single_account_missing_account_number_raises_adapter_unavailable(monkeypatch):
    accounts_body = {"data": {"accounts": [{"accountName": "Primary", "accountType": "SAVINGS"}]}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=accounts_body))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {}))

    assert len(calls) == 1


_MULTI_ACCOUNTS_BODY = {
    "data": {
        "accounts": [
            {
                "accountNumber": "111",
                "accountName": "Savings",
                "accountType": "SAVINGS",
                "balance": "100.00",
                "cards": ["c1"],
                "branchName": "Downtown",
            },
            {
                "accountNumber": "222",
                "accountName": "Checking",
                "accountType": "CURRENT",
                "balance": "50.00",
                "cards": [],
                "branchName": "Uptown",
            },
        ]
    }
}
_MULTI_ACCOUNTS_TRIMMED = [
    {"accountNumber": "111", "accountName": "Savings", "accountType": "SAVINGS", "balance": "100.00"},
    {"accountNumber": "222", "accountName": "Checking", "accountType": "CURRENT", "balance": "50.00"},
]


def test_balance_adapter_multiple_accounts_raises_account_selection_required(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=_MULTI_ACCOUNTS_BODY))

    with pytest.raises(AdapterAccountSelectionRequiredError) as exc_info:
        asyncio.run(real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {}))

    assert exc_info.value.accounts == _MULTI_ACCOUNTS_TRIMMED
    for account in exc_info.value.accounts:
        assert set(account.keys()) == {"accountNumber", "accountName", "accountType", "balance"}
    assert len(calls) == 1


def test_transaction_history_adapter_multiple_accounts_raises_account_selection_required(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=_MULTI_ACCOUNTS_BODY))

    with pytest.raises(AdapterAccountSelectionRequiredError) as exc_info:
        asyncio.run(
            real.transaction_history_adapter.fulfill(_IDENTITY, _JWT, "transaction_history", {})
        )

    assert exc_info.value.accounts == _MULTI_ACCOUNTS_TRIMMED
    for account in exc_info.value.accounts:
        assert set(account.keys()) == {"accountNumber", "accountName", "accountType", "balance"}
    assert len(calls) == 1


@pytest.mark.parametrize(
    "malformed_body",
    [
        {},
        {"data": {}},
        {"data": {"accounts": "not-a-list"}},
        {"data": {"accounts": None}},
        {"data": {"accounts": 42}},
    ],
)
def test_balance_adapter_malformed_accounts_response_raises_adapter_unavailable(monkeypatch, malformed_body):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=malformed_body))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {}))

    assert len(calls) == 1


@pytest.mark.parametrize(
    "malformed_body",
    [
        {},
        {"data": {}},
        {"data": {"accounts": "not-a-list"}},
        {"data": {"accounts": None}},
    ],
)
def test_transaction_history_adapter_malformed_accounts_response_raises_adapter_unavailable(
    monkeypatch, malformed_body
):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=malformed_body))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.transaction_history_adapter.fulfill(_IDENTITY, _JWT, "transaction_history", {}))

    assert len(calls) == 1


# --- T-31: AsyncClient must be constructed with a timeout above httpx's
# 5.0s default (too short for the real bank platform's observed latency) --


def test_call_constructs_asyncclient_with_timeout_above_httpx_default(monkeypatch):
    """Regression test for T-31: _call()'s httpx.AsyncClient(...) previously
    omitted timeout=, silently falling back to httpx's 5.0s default. This
    captures the actual kwargs AsyncClient is constructed with (not just the
    request outcome, which the other tests in this file already cover) so a
    future edit that drops or shrinks timeout= fails loudly here instead of
    reappearing as sporadic AdapterUnavailableError against the real platform."""
    captured_kwargs = {}
    original_init = httpx.AsyncClient.__init__

    def fake_init(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", fake_init)
    _install_request(monkeypatch, response=FakeResponse(json_data={"data": {}}))

    asyncio.run(real.accounts_adapter.fulfill(_IDENTITY, _JWT, "accounts", {}))

    assert "timeout" in captured_kwargs
    assert captured_kwargs["timeout"] == 30.0
    assert captured_kwargs["timeout"] > 5.0  # httpx.AsyncClient's own default


def test_real_adapters_dict_has_exactly_the_five_expected_keys():
    assert set(real.REAL_ADAPTERS.keys()) == {
        "real:balance",
        "real:transaction_history",
        "real:accounts",
        "real:device_history",
        "real:login_history",
    }
    assert real.REAL_ADAPTERS["real:balance"] is real.balance_adapter
    assert real.REAL_ADAPTERS["real:transaction_history"] is real.transaction_history_adapter
    assert real.REAL_ADAPTERS["real:accounts"] is real.accounts_adapter
    assert real.REAL_ADAPTERS["real:device_history"] is real.device_history_adapter
    assert real.REAL_ADAPTERS["real:login_history"] is real.login_history_adapter
