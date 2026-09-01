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
from app.banking.adapters.base import AdapterAuthError, AdapterResult, AdapterUnavailableError
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


def test_balance_adapter_missing_account_number_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.balance_adapter.fulfill(_IDENTITY, _JWT, "balance", {}))

    assert calls == []


def test_transaction_history_adapter_returns_whole_body_on_success(monkeypatch):
    body = {"data": {"transactions": [{"id": "tx-1"}]}}
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history", {"accountNumber": "111"}
        )
    )

    assert result == AdapterResult(data=body)


def test_transaction_history_adapter_missing_account_number_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(
            real.transaction_history_adapter.fulfill(_IDENTITY, _JWT, "transaction_history", {})
        )

    assert calls == []


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


def test_device_history_adapter_returns_whole_body_on_success(monkeypatch):
    body = {"data": {"devices": []}}
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.device_history_adapter.fulfill(_IDENTITY, _JWT, "device_history", None))

    assert result == AdapterResult(data=body)


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
