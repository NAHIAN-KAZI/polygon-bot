"""Tests for app/banking/adapters/real.py: the real adapters (balance,
transaction_history, accounts, device_history, login_history, beneficiary,
fee_quote, my_loans, fd_profit_history, dps_profit_history, disputes, cards,
plus the 2 MUTATING exceptions frezz_unfrezz/FreezeCardAdapter and
beneficiary_add/BeneficiaryAddAdapter) that call the platform API via a
shared _call() helper.

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
    AdapterValidationError,
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
    ("beneficiary_adapter", {}),
    ("cards_adapter", {}),
    ("freeze_card_adapter", {"cardId": "41", "verificationToken": "tok-1", "pin": "123456"}),
    ("beneficiary_add_adapter", {"serviceType": "OTHER_BANK", "nickname": "Test"}),
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


def _install_sequential_responses(monkeypatch, responses):
    """Like _install_request, but returns each response in `responses` in
    call order regardless of path -- for T-33's date-range paging, where the
    same path is hit repeatedly with different page params so routing by
    path alone (as _install_path_responses does) can't distinguish calls."""
    calls = []
    it = iter(responses)

    async def fake_request(self, method, path, *, headers=None, params=None, json=None):
        calls.append(
            {"method": method, "path": path, "headers": headers, "params": params, "json": json}
        )
        return next(it)

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


def test_real_adapters_dict_has_exactly_the_thirty_one_expected_keys():
    # T-57/T-60: cards, frezz_unfrezz (freeze card, MUTATING), beneficiary_add
    # (MUTATING) added. T-64: 17 read-only GET adapters added (identity of
    # each T-64 entry is asserted in tests/test_real_adapters_t64.py).
    assert len(real.REAL_ADAPTERS) == 31
    assert set(real.REAL_ADAPTERS.keys()) == {
        "real:balance",
        "real:transaction_history",
        "real:accounts",
        "real:device_history",
        "real:login_history",
        "real:beneficiary",
        "real:fee_quote",
        "real:my_loans",
        "real:fd_profit_history",
        "real:dps_profit_history",
        "real:disputes",
        "real:cards",
        "real:frezz_unfrezz",
        "real:beneficiary_add",
        "real:my_tickets",
        "real:account_transactions",
        "real:card_limit_requests",
        "real:card_products",
        "real:virtual_card_requests",
        "real:replacement_requests",
        "real:credit_card_summary",
        "real:credit_card_statement",
        "real:profile",
        "real:address",
        "real:contacts",
        "real:profile_change_requests",
        "real:contact_priority_requests",
        "real:gifts_received",
        "real:email_transfers",
        "real:qr_payment_history",
        "real:transfer_limit",
    }
    assert real.REAL_ADAPTERS["real:balance"] is real.balance_adapter
    assert real.REAL_ADAPTERS["real:transaction_history"] is real.transaction_history_adapter
    assert real.REAL_ADAPTERS["real:accounts"] is real.accounts_adapter
    assert real.REAL_ADAPTERS["real:device_history"] is real.device_history_adapter
    assert real.REAL_ADAPTERS["real:login_history"] is real.login_history_adapter
    assert real.REAL_ADAPTERS["real:beneficiary"] is real.beneficiary_adapter
    assert real.REAL_ADAPTERS["real:fee_quote"] is real.fees_adapter
    assert real.REAL_ADAPTERS["real:my_loans"] is real.loans_adapter
    assert real.REAL_ADAPTERS["real:fd_profit_history"] is real.fd_profit_history_adapter
    assert real.REAL_ADAPTERS["real:dps_profit_history"] is real.dps_profit_history_adapter
    assert real.REAL_ADAPTERS["real:disputes"] is real.disputes_adapter
    assert real.REAL_ADAPTERS["real:cards"] is real.cards_adapter
    assert real.REAL_ADAPTERS["real:frezz_unfrezz"] is real.freeze_card_adapter
    assert real.REAL_ADAPTERS["real:beneficiary_add"] is real.beneficiary_add_adapter


# --- T-37/T-38: BeneficiaryAdapter -------------------------------------------


def test_beneficiary_adapter_no_payload_omits_service_type_param_and_wraps_bare_array(monkeypatch):
    """T-38: GET /beneficiary/v1/beneficiaries returns a bare JSON array
    (live-confirmed), so fulfill() must wrap it under a "beneficiaries" key,
    mirroring DeviceHistoryAdapter's "devices" wrap."""
    body = [{"id": "ben-1"}]
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.beneficiary_adapter.fulfill(_IDENTITY, _JWT, "beneficiary", None))

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/beneficiary/v1/beneficiaries"
    assert calls[0]["params"] is None
    assert result == AdapterResult(data={"beneficiaries": body})
    assert isinstance(result.data, dict)


def test_beneficiary_adapter_empty_payload_omits_service_type_param(monkeypatch):
    body = []
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.beneficiary_adapter.fulfill(_IDENTITY, _JWT, "beneficiary", {}))

    assert len(calls) == 1
    assert calls[0]["params"] is None
    assert result == AdapterResult(data={"beneficiaries": body})


def test_beneficiary_adapter_forwards_service_type_param(monkeypatch):
    body = [{"id": "ben-1", "serviceType": "OWN_BANK"}]
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.beneficiary_adapter.fulfill(
            _IDENTITY, _JWT, "beneficiary", {"serviceType": "OWN_BANK"}
        )
    )

    assert len(calls) == 1
    assert calls[0]["path"] == "/beneficiary/v1/beneficiaries"
    assert calls[0]["params"] == {"serviceType": "OWN_BANK"}
    assert result == AdapterResult(data={"beneficiaries": body})


# --- T-33: date-range filtering (_fetch_all_pages / _filter_by_date_range /
# _fetch_and_filter_date_range) plus its wiring into TransactionHistoryAdapter
# and LoginHistoryAdapter.fulfill --------------------------------------------


def test_fetch_all_pages_stops_on_has_next_false(monkeypatch):
    body = {
        "transactions": [{"id": f"tx-{i}"} for i in range(10)],
        "pagination": {"hasNext": False},
    }
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    items = asyncio.run(
        real._fetch_all_pages("GET", "/some/path", _JWT, {"accountNumber": "111"}, "transactions")
    )

    assert len(calls) == 1
    assert calls[0]["params"] == {"accountNumber": "111", "page": 0, "size": 50}
    assert len(items) == 10


def test_fetch_all_pages_stops_at_record_cap_without_fetching_extra_page(monkeypatch):
    """200-record cap: pages keep returning 50 records with hasNext always
    true. Must stop once 200 records are accumulated (after 4 pages) rather
    than fetching a 5th (or later, an 11th) page."""
    page_body = {
        "transactions": [{"id": f"tx-{i}"} for i in range(50)],
        "pagination": {"hasNext": True},
    }
    responses = [FakeResponse(json_data=page_body) for _ in range(20)]
    calls = _install_sequential_responses(monkeypatch, responses)

    items = asyncio.run(real._fetch_all_pages("GET", "/some/path", _JWT, {}, "transactions"))

    assert len(items) == 200
    assert len(calls) == 4
    assert [c["params"]["page"] for c in calls] == [0, 1, 2, 3]


def test_fetch_all_pages_stops_at_page_cap_without_infinite_loop(monkeypatch):
    """10-page cap: each page returns only 1 record (never hits the 200
    record cap) with hasNext always true. Must stop after 10 pages instead
    of looping forever."""
    page_body = {
        "transactions": [{"id": "tx-1"}],
        "pagination": {"hasNext": True},
    }
    responses = [FakeResponse(json_data=page_body) for _ in range(50)]
    calls = _install_sequential_responses(monkeypatch, responses)

    items = asyncio.run(real._fetch_all_pages("GET", "/some/path", _JWT, {}, "transactions"))

    assert len(items) == 10
    assert len(calls) == 10
    assert [c["params"]["page"] for c in calls] == list(range(10))


def test_filter_by_date_range_includes_start_and_end_boundary_inclusive():
    items = [
        {"txnTime": "2026-01-10T00:00:00Z"},
        {"txnTime": "2026-01-12T23:59:59Z"},
    ]

    filtered = real._filter_by_date_range(items, "txnTime", "2026-01-10", "2026-01-12")

    assert filtered == items


def test_filter_by_date_range_excludes_items_outside_range():
    items = [
        {"txnTime": "2026-01-09T23:59:59Z"},
        {"txnTime": "2026-01-13T00:00:00Z"},
    ]

    filtered = real._filter_by_date_range(items, "txnTime", "2026-01-10", "2026-01-12")

    assert filtered == []


def test_filter_by_date_range_parses_z_suffix_and_offset_timestamps():
    items = [
        {"txnTime": "2026-01-10T00:00:00Z"},
        {"txnTime": "2026-01-10T06:00:00+06:00"},  # same instant as UTC midnight
        {"txnTime": "2026-01-13T05:59:00+06:00"},  # == 2026-01-12T23:59:00Z
    ]

    filtered = real._filter_by_date_range(items, "txnTime", "2026-01-10", "2026-01-12")

    assert len(filtered) == 3


def test_filter_by_date_range_skips_items_missing_timestamp():
    present = {"txnTime": "2026-01-10T00:00:00Z"}
    items = [{"other": "field"}, present]

    filtered = real._filter_by_date_range(items, "txnTime", "2026-01-10", "2026-01-12")

    assert filtered == [present]


def test_filter_by_date_range_malformed_timestamp_raises_rather_than_skipping():
    """_filter_by_date_range has no per-item try/except -- an unparseable
    timestamp raises ValueError out of the whole filter call (this is what
    the adapter-level except Exception: pass around
    _fetch_and_filter_date_range is there to catch)."""
    items = [
        {"txnTime": "2026-01-11T00:00:00Z"},  # would otherwise be included
        {"txnTime": "not-a-timestamp"},
    ]

    with pytest.raises(ValueError):
        real._filter_by_date_range(items, "txnTime", "2026-01-10", "2026-01-12")


def test_fetch_and_filter_date_range_returns_filtered_shape(monkeypatch):
    body = {
        "transactions": [
            {"id": "tx-in", "txnTime": "2026-01-11T00:00:00Z"},
            {"id": "tx-out", "txnTime": "2026-02-01T00:00:00Z"},
        ],
        "pagination": {"hasNext": False},
    }
    _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real._fetch_and_filter_date_range(
            "GET", "/some/path", _JWT, {"accountNumber": "111"}, "transactions", "txnTime",
            "2026-01-10", "2026-01-12",
        )
    )

    assert result["dateFiltered"] is True
    assert result["transactions"] == [body["transactions"][0]]
    assert result["pagination"] == {"totalCount": 1}


# --- T-33: TransactionHistoryAdapter.fulfill date-range wiring --------------


def test_transaction_history_adapter_date_range_happy_path(monkeypatch):
    body = {
        "transactions": [
            {"id": "tx-in", "txnTime": "2026-01-11T00:00:00Z"},
            {"id": "tx-out", "txnTime": "2026-02-01T00:00:00Z"},
        ],
        "pagination": {"hasNext": False},
    }
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history",
            {"accountNumber": "111", "startDate": "2026-01-10", "endDate": "2026-01-12"},
        )
    )

    assert result.data["dateFiltered"] is True
    assert result.data["transactions"] == [body["transactions"][0]]
    assert result.data["pagination"] == {"totalCount": 1}
    assert len(calls) == 1
    assert calls[0]["path"] == "/transfer/v1/accounting/transaction-list"
    assert calls[0]["params"] == {"accountNumber": "111", "page": 0, "size": 50}


def test_transaction_history_adapter_only_start_date_falls_back_to_single_page(monkeypatch):
    body = {"data": {"transactions": []}}
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history",
            {"accountNumber": "111", "startDate": "2026-01-10"},
        )
    )

    assert len(calls) == 1
    assert calls[0]["params"] == {"accountNumber": "111", "page": 0, "size": 10}
    assert result == AdapterResult(data=body)


def test_transaction_history_adapter_only_end_date_falls_back_to_single_page(monkeypatch):
    body = {"data": {"transactions": []}}
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history",
            {"accountNumber": "111", "endDate": "2026-01-12"},
        )
    )

    assert len(calls) == 1
    assert calls[0]["params"] == {"accountNumber": "111", "page": 0, "size": 10}
    assert result == AdapterResult(data=body)


def test_transaction_history_adapter_neither_date_uses_original_single_page_params(monkeypatch):
    body = {"data": {"transactions": []}}
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history", {"accountNumber": "111"}
        )
    )

    assert len(calls) == 1
    assert calls[0]["params"] == {"accountNumber": "111", "page": 0, "size": 10}
    assert result == AdapterResult(data=body)


def test_transaction_history_adapter_date_range_failure_falls_back_to_single_page(monkeypatch):
    date_range_body = {
        "transactions": [{"id": "tx-1", "txnTime": "not-a-timestamp"}],
        "pagination": {"hasNext": False},
    }
    fallback_body = {"data": {"transactions": [{"id": "tx-1"}]}}
    calls = _install_sequential_responses(
        monkeypatch, [FakeResponse(json_data=date_range_body), FakeResponse(json_data=fallback_body)]
    )

    result = asyncio.run(
        real.transaction_history_adapter.fulfill(
            _IDENTITY, _JWT, "transaction_history",
            {"accountNumber": "111", "startDate": "2026-01-10", "endDate": "2026-01-12"},
        )
    )

    assert len(calls) == 2
    assert calls[0]["params"] == {"accountNumber": "111", "page": 0, "size": 50}
    assert calls[1]["params"] == {"accountNumber": "111", "page": 0, "size": 10}
    assert result == AdapterResult(data=fallback_body)


# --- T-33: LoginHistoryAdapter.fulfill date-range wiring --------------------


def test_login_history_adapter_date_range_happy_path(monkeypatch):
    body = {
        "records": [
            {"id": "login-in", "loginAt": "2026-01-11T00:00:00Z"},
            {"id": "login-out", "loginAt": "2026-02-01T00:00:00Z"},
        ],
        "pagination": {"hasNext": False},
    }
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.login_history_adapter.fulfill(
            _IDENTITY, _JWT, "login_history",
            {"deviceId": "dev-1", "startDate": "2026-01-10", "endDate": "2026-01-12"},
        )
    )

    assert result.data["dateFiltered"] is True
    assert result.data["records"] == [body["records"][0]]
    assert result.data["pagination"] == {"totalCount": 1}
    assert len(calls) == 1
    assert calls[0]["path"] == "/auth/v1/devices/dev-1/login-history"
    assert calls[0]["params"] == {"page": 0, "size": 50}


def test_login_history_adapter_only_start_date_falls_back_to_single_page(monkeypatch):
    body = {"data": {"logins": []}}
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.login_history_adapter.fulfill(
            _IDENTITY, _JWT, "login_history",
            {"deviceId": "dev-1", "startDate": "2026-01-10"},
        )
    )

    assert len(calls) == 1
    assert calls[0]["params"] == {"page": 0, "size": 20}
    assert result == AdapterResult(data=body)


def test_login_history_adapter_only_end_date_falls_back_to_single_page(monkeypatch):
    body = {"data": {"logins": []}}
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.login_history_adapter.fulfill(
            _IDENTITY, _JWT, "login_history",
            {"deviceId": "dev-1", "endDate": "2026-01-12"},
        )
    )

    assert len(calls) == 1
    assert calls[0]["params"] == {"page": 0, "size": 20}
    assert result == AdapterResult(data=body)


def test_login_history_adapter_neither_date_uses_original_single_page_params(monkeypatch):
    body = {"data": {"logins": []}}
    calls = _install_sequential_responses(monkeypatch, [FakeResponse(json_data=body)])

    result = asyncio.run(
        real.login_history_adapter.fulfill(
            _IDENTITY, _JWT, "login_history", {"deviceId": "dev-1"}
        )
    )

    assert len(calls) == 1
    assert calls[0]["params"] == {"page": 0, "size": 20}
    assert result == AdapterResult(data=body)


def test_login_history_adapter_date_range_failure_falls_back_to_single_page(monkeypatch):
    date_range_body = {
        "records": [{"id": "login-1", "loginAt": "not-a-timestamp"}],
        "pagination": {"hasNext": False},
    }
    fallback_body = {"data": {"logins": [{"id": "login-1"}]}}
    calls = _install_sequential_responses(
        monkeypatch, [FakeResponse(json_data=date_range_body), FakeResponse(json_data=fallback_body)]
    )

    result = asyncio.run(
        real.login_history_adapter.fulfill(
            _IDENTITY, _JWT, "login_history",
            {"deviceId": "dev-1", "startDate": "2026-01-10", "endDate": "2026-01-12"},
        )
    )

    assert len(calls) == 2
    assert calls[0]["params"] == {"page": 0, "size": 50}
    assert calls[1]["params"] == {"page": 0, "size": 20}
    assert result == AdapterResult(data=fallback_body)


# --- T-41: FeesAdapter --------------------------------------------------------


def test_fees_adapter_valid_payload_converts_taka_to_poisha_and_forwards_params(monkeypatch):
    body = {"data": {"charge": "5.75"}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.fees_adapter.fulfill(
            _IDENTITY, _JWT, "fee_quote", {"transactionType": "bkash", "amount": 500}
        )
    )

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/transfer/v1/transaction-type/charge-with-amount"
    assert calls[0]["params"] == {"appSettingsId": "bkash", "amount": 50000}
    assert result == AdapterResult(data=body)


def test_fees_adapter_missing_transaction_type_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.fees_adapter.fulfill(_IDENTITY, _JWT, "fee_quote", {"amount": 500}))

    assert calls == []


def test_fees_adapter_missing_amount_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(
            real.fees_adapter.fulfill(_IDENTITY, _JWT, "fee_quote", {"transactionType": "bkash"})
        )

    assert calls == []


def test_fees_adapter_none_payload_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.fees_adapter.fulfill(_IDENTITY, _JWT, "fee_quote", None))

    assert calls == []


def test_fees_adapter_404_propagates_as_adapter_unavailable_error(monkeypatch):
    # FeesAdapter has no special-cased error handling of its own -- this
    # confirms _call()'s existing generic non-2xx behavior (see the
    # test_500_raises_adapter_unavailable_error parametrized test above)
    # already covers it.
    calls = _install_request(monkeypatch, response=FakeResponse(status_code=404))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(
            real.fees_adapter.fulfill(
                _IDENTITY, _JWT, "fee_quote", {"transactionType": "bkash", "amount": 500}
            )
        )

    assert len(calls) == 1


# --- T-58: LoansAdapter -------------------------------------------------------


def test_loans_adapter_returns_whole_body_on_success(monkeypatch):
    body = {"data": {"loans": [{"id": "loan-1"}]}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.loans_adapter.fulfill(_IDENTITY, _JWT, "my_loans", {}))

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/loan/v1/loans"
    assert result == AdapterResult(data=body)


def test_loans_adapter_empty_list_is_a_clean_success_not_a_failure(monkeypatch):
    body = {"data": {"loans": []}}
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.loans_adapter.fulfill(_IDENTITY, _JWT, "my_loans", None))

    assert result == AdapterResult(data=body)


def test_loans_adapter_401_raises_adapter_auth_error(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(status_code=401))

    with pytest.raises(AdapterAuthError):
        asyncio.run(real.loans_adapter.fulfill(_IDENTITY, _JWT, "my_loans", {}))


def test_loans_adapter_wraps_bare_array_response_under_loans_key(monkeypatch):
    """Live-confirmed 2026-10-01: GET /loan/v1/loans returns a bare JSON array
    (not an object), same shape as devices/beneficiaries -- must be wrapped so
    callers always get a dict (app/routes/chat.py calls data.get(...))."""
    body = [{"id": "loan-1"}, {"id": "loan-2"}]
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.loans_adapter.fulfill(_IDENTITY, _JWT, "my_loans", {}))

    assert result == AdapterResult(data={"loans": body})
    assert isinstance(result.data, dict)


# --- T-58: FdProfitHistoryAdapter / DpsProfitHistoryAdapter -------------------


def test_fd_profit_history_adapter_explicit_id_skips_accounts_lookup(monkeypatch):
    body = {"data": {"history": []}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.fd_profit_history_adapter.fulfill(
            _IDENTITY, _JWT, "fd_profit_history", {"id": "FDDE1F32376C574CB9"}
        )
    )

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/product/v1/fixed-deposit/FDDE1F32376C574CB9/profit-history"
    assert result == AdapterResult(data=body)


def test_fd_profit_history_adapter_explicit_identifier_key_also_accepted(monkeypatch):
    body = {"data": {"history": []}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    asyncio.run(
        real.fd_profit_history_adapter.fulfill(
            _IDENTITY, _JWT, "fd_profit_history", {"identifier": "FDDE1F32376C574CB9"}
        )
    )

    assert calls[0]["path"] == "/product/v1/fixed-deposit/FDDE1F32376C574CB9/profit-history"


_LEDGER_ACCOUNTS_ONE_FD_ONE_DPS = {
    "data": {
        "ledgerAccounts": [
            {"chartOfAccountName": "Fixed Deposit", "identifier": "FDDE1F32376C574CB9"},
            {"chartOfAccountName": "DPS Deposit", "identifier": "DPS412939644D894570"},
            {"chartOfAccountName": "Savings", "identifier": "SAV123"},
        ]
    }
}


def test_fd_profit_history_adapter_single_match_auto_resolves_transparently(monkeypatch):
    history_body = {"data": {"history": [{"id": "p-1"}]}}
    calls = _install_path_responses(
        monkeypatch,
        {
            "/polygon-bank/v1/accounts": FakeResponse(json_data=_LEDGER_ACCOUNTS_ONE_FD_ONE_DPS),
            "/product/v1/fixed-deposit/FDDE1F32376C574CB9/profit-history": FakeResponse(
                json_data=history_body
            ),
        },
    )

    result = asyncio.run(
        real.fd_profit_history_adapter.fulfill(_IDENTITY, _JWT, "fd_profit_history", {})
    )

    assert result == AdapterResult(data=history_body)
    assert len(calls) == 2
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"
    assert calls[1]["path"] == "/product/v1/fixed-deposit/FDDE1F32376C574CB9/profit-history"


def test_dps_profit_history_adapter_single_match_auto_resolves_transparently(monkeypatch):
    history_body = {"data": {"history": [{"id": "p-1"}]}}
    calls = _install_path_responses(
        monkeypatch,
        {
            "/polygon-bank/v1/accounts": FakeResponse(json_data=_LEDGER_ACCOUNTS_ONE_FD_ONE_DPS),
            "/product/v1/dps/DPS412939644D894570/profit-history": FakeResponse(
                json_data=history_body
            ),
        },
    )

    result = asyncio.run(
        real.dps_profit_history_adapter.fulfill(_IDENTITY, _JWT, "dps_profit_history", None)
    )

    assert result == AdapterResult(data=history_body)
    assert len(calls) == 2
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"
    assert calls[1]["path"] == "/product/v1/dps/DPS412939644D894570/profit-history"


def test_fd_profit_history_adapter_zero_matches_raises_adapter_unavailable(monkeypatch):
    accounts_body = {"data": {"ledgerAccounts": [{"chartOfAccountName": "Savings", "identifier": "SAV123"}]}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=accounts_body))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.fd_profit_history_adapter.fulfill(_IDENTITY, _JWT, "fd_profit_history", {}))

    assert len(calls) == 1


def test_dps_profit_history_adapter_zero_matches_raises_adapter_unavailable(monkeypatch):
    accounts_body = {"data": {"ledgerAccounts": [{"chartOfAccountName": "Savings", "identifier": "SAV123"}]}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=accounts_body))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.dps_profit_history_adapter.fulfill(_IDENTITY, _JWT, "dps_profit_history", {}))

    assert len(calls) == 1


def test_fd_profit_history_adapter_multiple_matches_raises_account_selection_required(monkeypatch):
    accounts_body = {
        "data": {
            "ledgerAccounts": [
                {"chartOfAccountName": "Fixed Deposit", "identifier": "FD-1"},
                {"chartOfAccountName": "Fixed Deposit", "identifier": "FD-2"},
            ]
        }
    }
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=accounts_body))

    with pytest.raises(AdapterAccountSelectionRequiredError) as exc_info:
        asyncio.run(real.fd_profit_history_adapter.fulfill(_IDENTITY, _JWT, "fd_profit_history", {}))

    assert exc_info.value.accounts == [
        {"identifier": "FD-1", "chartOfAccountName": "Fixed Deposit"},
        {"identifier": "FD-2", "chartOfAccountName": "Fixed Deposit"},
    ]
    assert len(calls) == 1


def test_fd_profit_history_adapter_malformed_ledger_accounts_raises_adapter_unavailable(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"data": {}}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.fd_profit_history_adapter.fulfill(_IDENTITY, _JWT, "fd_profit_history", {}))

    assert len(calls) == 1


def test_fd_profit_history_adapter_wraps_bare_array_response(monkeypatch):
    body = [{"month": "2026-09", "profit": "12.50"}]
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.fd_profit_history_adapter.fulfill(
            _IDENTITY, _JWT, "fd_profit_history", {"id": "FD-1"}
        )
    )

    assert result == AdapterResult(data={"profitHistory": body})
    assert isinstance(result.data, dict)


def test_dps_profit_history_adapter_wraps_bare_array_response(monkeypatch):
    body = [{"month": "2026-09", "profit": "5.00"}]
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.dps_profit_history_adapter.fulfill(
            _IDENTITY, _JWT, "dps_profit_history", {"id": "DPS-1"}
        )
    )

    assert result == AdapterResult(data={"profitHistory": body})
    assert isinstance(result.data, dict)


# --- T-58: DisputesAdapter -----------------------------------------------------


def test_disputes_adapter_uses_resolved_account_number_as_query_param(monkeypatch):
    body = {"data": {"disputes": []}}
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.disputes_adapter.fulfill(_IDENTITY, _JWT, "disputes", {"accountNumber": "111"})
    )

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/service-request/v1/disputes"
    assert calls[0]["params"] == {"accountNumber": "111"}
    assert result == AdapterResult(data=body)


def test_disputes_adapter_auto_resolves_account_number_when_omitted(monkeypatch):
    accounts_body = {
        "data": {
            "accounts": [
                {"accountNumber": "999", "accountName": "Primary", "accountType": "SAVINGS", "balance": "10.00"}
            ]
        }
    }
    disputes_body = {"data": {"disputes": []}}
    calls = _install_path_responses(
        monkeypatch,
        {
            "/polygon-bank/v1/accounts": FakeResponse(json_data=accounts_body),
            "/service-request/v1/disputes": FakeResponse(json_data=disputes_body),
        },
    )

    result = asyncio.run(real.disputes_adapter.fulfill(_IDENTITY, _JWT, "disputes", {}))

    assert result == AdapterResult(data=disputes_body)
    assert len(calls) == 2
    assert calls[1]["params"] == {"accountNumber": "999"}


def test_disputes_adapter_empty_list_is_a_clean_success_not_a_failure(monkeypatch):
    body = {"data": {"disputes": []}}
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.disputes_adapter.fulfill(_IDENTITY, _JWT, "disputes", {"accountNumber": "111"})
    )

    assert result == AdapterResult(data=body)


def test_disputes_adapter_wraps_bare_array_response(monkeypatch):
    body = [{"id": "dispute-1"}]
    _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(
        real.disputes_adapter.fulfill(_IDENTITY, _JWT, "disputes", {"accountNumber": "111"})
    )

    assert result == AdapterResult(data={"disputes": body})
    assert isinstance(result.data, dict)


# --- T-57: CardsAdapter (read-only) ------------------------------------------


def test_cards_adapter_flattens_cards_across_all_accounts(monkeypatch):
    accounts_body = {
        "data": {
            "accounts": [
                {
                    "accountNumber": "111",
                    "cards": [
                        {"id": "41", "cardNumber": "4001****0251", "cardType": "DEBIT", "status": "ACTIVE"},
                    ],
                },
                {
                    "accountNumber": "222",
                    "cards": [
                        {"id": "42", "cardNumber": "4002****0252", "cardType": "DEBIT", "status": "FROZEN"},
                    ],
                },
            ]
        }
    }
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=accounts_body))

    result = asyncio.run(real.cards_adapter.fulfill(_IDENTITY, _JWT, "cards", None))

    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/polygon-bank/v1/accounts"
    assert result == AdapterResult(
        data={
            "cards": [
                {"id": "41", "cardNumber": "4001****0251", "cardType": "DEBIT", "status": "ACTIVE"},
                {"id": "42", "cardNumber": "4002****0252", "cardType": "DEBIT", "status": "FROZEN"},
            ]
        }
    )


def test_cards_adapter_account_with_no_cards_key_contributes_nothing(monkeypatch):
    accounts_body = {"data": {"accounts": [{"accountNumber": "111"}]}}
    _install_request(monkeypatch, response=FakeResponse(json_data=accounts_body))

    result = asyncio.run(real.cards_adapter.fulfill(_IDENTITY, _JWT, "cards", None))

    assert result == AdapterResult(data={"cards": []})


def test_cards_adapter_zero_accounts_returns_empty_cards_list_not_a_failure(monkeypatch):
    accounts_body = {"data": {"accounts": []}}
    _install_request(monkeypatch, response=FakeResponse(json_data=accounts_body))

    result = asyncio.run(real.cards_adapter.fulfill(_IDENTITY, _JWT, "cards", {}))

    assert result == AdapterResult(data={"cards": []})


def test_cards_adapter_malformed_accounts_response_returns_empty_cards_list(monkeypatch):
    # Unlike balance/transaction_history (which need a specific account to
    # act on and so must fail loudly when accounts are malformed), cards is
    # a pure aggregation across whatever accounts exist -- malformed/missing
    # accounts just means no cards to show, not a service failure.
    _install_request(monkeypatch, response=FakeResponse(json_data={"data": {}}))

    result = asyncio.run(real.cards_adapter.fulfill(_IDENTITY, _JWT, "cards", {}))

    assert result == AdapterResult(data={"cards": []})


# --- T-57: FreezeCardAdapter (MUTATING -- mocked HTTP only, never live) -----


def test_freeze_card_adapter_sends_exact_documented_body_shape(monkeypatch):
    calls = _install_request(
        monkeypatch, response=FakeResponse(json_data={"id": "41", "status": "FROZEN"})
    )

    result = asyncio.run(
        real.freeze_card_adapter.fulfill(
            _IDENTITY, _JWT, "frezz_unfrezz",
            {"cardId": "41", "verificationToken": "tok-123", "pin": "123456"},
        )
    )

    assert len(calls) == 1
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["path"] == "/card/v1/cards/41/freeze"
    assert calls[0]["json"] == {
        "reasonCode": "OTHER",
        "verificationToken": "tok-123",
        "pin": "123456",
    }
    assert calls[0]["headers"] == {"Authorization": f"Bearer {_JWT}"}
    assert result == AdapterResult(data={"id": "41", "status": "FROZEN"})


def test_freeze_card_adapter_sends_password_variant_body_shape(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"status": "FROZEN"}))

    asyncio.run(
        real.freeze_card_adapter.fulfill(
            _IDENTITY, _JWT, "frezz_unfrezz",
            {"cardId": "41", "verificationToken": "tok-123", "password": "hunter2"},
        )
    )

    assert calls[0]["json"] == {
        "reasonCode": "OTHER",
        "verificationToken": "tok-123",
        "password": "hunter2",
    }
    assert "pin" not in calls[0]["json"]


def test_freeze_card_adapter_accepts_id_key_as_alias_for_card_id(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"status": "FROZEN"}))

    asyncio.run(
        real.freeze_card_adapter.fulfill(
            _IDENTITY, _JWT, "frezz_unfrezz",
            {"id": "41", "verificationToken": "tok-123", "pin": "123456"},
        )
    )

    assert calls[0]["path"] == "/card/v1/cards/41/freeze"


def test_freeze_card_adapter_forwards_optional_pin(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"status": "FROZEN"}))

    asyncio.run(
        real.freeze_card_adapter.fulfill(
            _IDENTITY, _JWT, "frezz_unfrezz",
            {"cardId": "41", "verificationToken": "tok-123", "pin": "123456"},
        )
    )

    assert calls[0]["json"] == {
        "reasonCode": "OTHER",
        "verificationToken": "tok-123",
        "pin": "123456",
    }


def test_freeze_card_adapter_never_forwards_free_text_reason_field(monkeypatch):
    # The real DTO has no free-text "reason" field (only the fixed-enum
    # reasonCode, always "OTHER" today) -- a conversationally-gathered
    # customer reason must never be invented into the request body.
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"status": "FROZEN"}))

    asyncio.run(
        real.freeze_card_adapter.fulfill(
            _IDENTITY, _JWT, "frezz_unfrezz",
            {
                "cardId": "41", "verificationToken": "tok-123", "pin": "123456",
                "reason": "lost my card",
            },
        )
    )

    assert calls[0]["json"] == {
        "reasonCode": "OTHER",
        "verificationToken": "tok-123",
        "pin": "123456",
    }
    assert "reason" not in calls[0]["json"]


def test_freeze_card_adapter_missing_card_id_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz", {"verificationToken": "tok-123"}
            )
        )

    assert calls == []


def test_freeze_card_adapter_missing_verification_token_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz", {"cardId": "41"}
            )
        )

    assert calls == []


def test_freeze_card_adapter_none_payload_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.freeze_card_adapter.fulfill(_IDENTITY, _JWT, "frezz_unfrezz", None))

    assert calls == []


def test_freeze_card_adapter_generic_401_raises_adapter_auth_error(monkeypatch):
    # No "message" field in the error body at all (or one that doesn't match
    # either documented freeze-specific 401 string) -- falls through to the
    # generic AdapterAuthError, same as every other real adapter's 401.
    _install_request(monkeypatch, response=FakeResponse(status_code=401))

    with pytest.raises(AdapterAuthError):
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz",
                {"cardId": "41", "verificationToken": "tok-123", "pin": "123456"},
            )
        )


def test_freeze_card_adapter_invalid_credentials_401_raises_adapter_validation_error(monkeypatch):
    _install_request(
        monkeypatch,
        response=FakeResponse(status_code=401, json_data={"message": "Invalid credentials"}),
    )

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz",
                {"cardId": "41", "verificationToken": "tok-123", "pin": "000000"},
            )
        )

    assert exc_info.value.reason == "INVALID_CREDENTIALS"


def test_freeze_card_adapter_invalid_or_expired_otp_401_raises_adapter_validation_error(monkeypatch):
    _install_request(
        monkeypatch,
        response=FakeResponse(
            status_code=401, json_data={"message": "Invalid or expired OTP verification"}
        ),
    )

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz",
                {"cardId": "41", "verificationToken": "stale-tok", "pin": "123456"},
            )
        )

    assert exc_info.value.reason == "INVALID_VERIFICATION_TOKEN"


def test_freeze_card_adapter_403_without_matching_message_raises_generic_auth_error(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(status_code=403, json_data={}))

    with pytest.raises(AdapterAuthError):
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz",
                {"cardId": "41", "verificationToken": "tok-123", "pin": "123456"},
            )
        )


def test_freeze_card_adapter_both_pin_and_password_raises_validation_error_without_http_call(
    monkeypatch,
):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz",
                {
                    "cardId": "41", "verificationToken": "tok-123",
                    "pin": "123456", "password": "hunter2",
                },
            )
        )

    assert exc_info.value.reason == "PIN_OR_PASSWORD_REQUIRED"
    assert calls == []


def test_freeze_card_adapter_neither_pin_nor_password_raises_validation_error_without_http_call(
    monkeypatch,
):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(
            real.freeze_card_adapter.fulfill(
                _IDENTITY, _JWT, "frezz_unfrezz",
                {"cardId": "41", "verificationToken": "tok-123"},
            )
        )

    assert exc_info.value.reason == "PIN_OR_PASSWORD_REQUIRED"
    assert calls == []


def test_freeze_card_adapter_bare_non_dict_response_wraps_under_result_key(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(json_data="OK"))

    result = asyncio.run(
        real.freeze_card_adapter.fulfill(
            _IDENTITY, _JWT, "frezz_unfrezz",
            {"cardId": "41", "verificationToken": "tok-123", "pin": "123456"},
        )
    )

    assert result == AdapterResult(data={"result": "OK"})


# --- T-60: BeneficiaryAddAdapter (MUTATING -- mocked HTTP only, never live) -


def test_beneficiary_add_adapter_sends_exact_documented_body_shape(monkeypatch):
    calls = _install_request(
        monkeypatch, response=FakeResponse(json_data={"id": "ben-1", "nickname": "Dipu"})
    )

    result = asyncio.run(
        real.beneficiary_add_adapter.fulfill(
            _IDENTITY, _JWT, "beneficiary_add",
            {
                "serviceType": "OTHER_BANK",
                "nickname": "Dipu",
                "identifierType": "ACCOUNT_NUMBER",
                "accountNumber": "1234567890",
                "accountHolderName": "Dipu Rahman",
                "bankName": "City Bank",
                "branchName": "Gulshan",
                "district": "Dhaka",
                "routingNumber": "123456789",
            },
        )
    )

    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/beneficiary/v1/beneficiaries"
    assert calls[0]["json"] == {
        "serviceType": "OTHER_BANK",
        "nickname": "Dipu",
        "identifierType": "ACCOUNT_NUMBER",
        "accountNumber": "1234567890",
        "accountHolderName": "Dipu Rahman",
        "bankName": "City Bank",
        "branchName": "Gulshan",
        "district": "Dhaka",
        "routingNumber": "123456789",
    }
    assert result == AdapterResult(data={"id": "ben-1", "nickname": "Dipu"})


def test_beneficiary_add_adapter_omits_unsupplied_optional_fields(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={"id": "ben-2"}))

    asyncio.run(
        real.beneficiary_add_adapter.fulfill(
            _IDENTITY, _JWT, "beneficiary_add",
            {"serviceType": "MFS", "nickname": "My bKash", "mfsProvider": "BKASH"},
        )
    )

    assert calls[0]["json"] == {
        "serviceType": "MFS",
        "nickname": "My bKash",
        "mfsProvider": "BKASH",
    }


def test_beneficiary_add_adapter_missing_service_type_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(
            real.beneficiary_add_adapter.fulfill(
                _IDENTITY, _JWT, "beneficiary_add", {"nickname": "Dipu"}
            )
        )

    assert calls == []


def test_beneficiary_add_adapter_missing_nickname_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(
            real.beneficiary_add_adapter.fulfill(
                _IDENTITY, _JWT, "beneficiary_add", {"serviceType": "OTHER_BANK"}
            )
        )

    assert calls == []


def test_beneficiary_add_adapter_none_payload_raises_without_http_call(monkeypatch):
    calls = _install_request(monkeypatch, response=FakeResponse(json_data={}))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.beneficiary_add_adapter.fulfill(_IDENTITY, _JWT, "beneficiary_add", None))

    assert calls == []


def test_beneficiary_add_adapter_401_raises_adapter_auth_error(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(status_code=401))

    with pytest.raises(AdapterAuthError):
        asyncio.run(
            real.beneficiary_add_adapter.fulfill(
                _IDENTITY, _JWT, "beneficiary_add",
                {"serviceType": "OTHER_BANK", "nickname": "Dipu"},
            )
        )


def test_beneficiary_add_adapter_existing_list_adapter_untouched(monkeypatch):
    # Regression guard: adding BeneficiaryAddAdapter must not change
    # BeneficiaryAdapter's own (list) behavior at all.
    body = [{"id": "ben-1"}]
    calls = _install_request(monkeypatch, response=FakeResponse(json_data=body))

    result = asyncio.run(real.beneficiary_adapter.fulfill(_IDENTITY, _JWT, "beneficiary", None))

    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/beneficiary/v1/beneficiaries"
    assert result == AdapterResult(data={"beneficiaries": body})


# --- T-57: send_otp() / verify_otp() (plain async helpers, not adapters) ----
# Per the task's security-critical testing constraint: every test below uses
# the same monkeypatched httpx.AsyncClient.request as the rest of this file
# -- no real HTTP call, and in particular no real call to otp/v1/send, is
# ever made by this test suite.


def test_send_otp_success_returns_none_and_sends_no_auth_header(monkeypatch):
    calls = _install_request(
        monkeypatch, response=FakeResponse(json_data={"message": "OTP sent successfully"})
    )

    result = asyncio.run(real.send_otp("01712345678"))

    assert result is None
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/otp/v1/send"
    assert calls[0]["json"] == {"phone": "01712345678"}
    assert calls[0]["headers"] is None  # public endpoint -- no JWT forwarded


def test_send_otp_400_raises_adapter_validation_error_invalid_phone(monkeypatch):
    _install_request(
        monkeypatch,
        response=FakeResponse(status_code=400, json_data={"message": "Invalid phone number"}),
    )

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(real.send_otp("not-a-phone"))

    assert exc_info.value.reason == "INVALID_PHONE"


def test_send_otp_429_raises_adapter_validation_error_send_throttled(monkeypatch):
    _install_request(
        monkeypatch,
        response=FakeResponse(status_code=429, json_data={"message": "Please wait before retrying"}),
    )

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(real.send_otp("01712345678"))

    assert exc_info.value.reason == "SEND_THROTTLED"
    assert exc_info.value.retry_after_seconds is None


def test_send_otp_503_raises_adapter_validation_error_send_unavailable(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(status_code=503, json_data={}))

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(real.send_otp("01712345678"))

    assert exc_info.value.reason == "SEND_UNAVAILABLE"


def test_send_otp_other_status_raises_adapter_unavailable_error(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(status_code=500))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.send_otp("01712345678"))


def test_send_otp_network_error_raises_adapter_unavailable_error_not_raw_httpx(monkeypatch):
    _install_request(monkeypatch, exception=httpx.ConnectError("connection refused"))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.send_otp("01712345678"))


def test_send_otp_401_403_are_not_specially_mapped_to_auth_error(monkeypatch):
    # send_otp/verify_otp are unauthenticated endpoints -- a 401/403 here is
    # not a "your JWT was rejected" case (there's no JWT involved at all), so
    # unlike _call(), these must NOT raise AdapterAuthError. Not documented by
    # the bank's contract, so it falls through to the generic
    # AdapterUnavailableError rather than being silently misclassified.
    _install_request(monkeypatch, response=FakeResponse(status_code=401))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.send_otp("01712345678"))


def test_verify_otp_success_returns_verification_token(monkeypatch):
    calls = _install_request(
        monkeypatch,
        response=FakeResponse(
            json_data={
                "verified": True,
                "message": "OTP verified",
                "verificationToken": "a1b2c3d4-0000-0000-0000-000000000000",
            }
        ),
    )

    token = asyncio.run(real.verify_otp("01712345678", "0000"))

    assert token == "a1b2c3d4-0000-0000-0000-000000000000"
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/otp/v1/verify"
    assert calls[0]["json"] == {"phone": "01712345678", "otp": "0000"}
    assert calls[0]["headers"] is None  # public endpoint -- no JWT forwarded


def test_verify_otp_success_missing_token_in_body_raises_adapter_unavailable_error(monkeypatch):
    _install_request(
        monkeypatch, response=FakeResponse(json_data={"verified": True, "message": "OTP verified"})
    )

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.verify_otp("01712345678", "0000"))


def test_verify_otp_400_raises_adapter_validation_error_with_attempts_remaining_parsed(monkeypatch):
    _install_request(
        monkeypatch,
        response=FakeResponse(
            status_code=400,
            json_data={"message": "Invalid OTP. 2 attempt(s) remaining."},
        ),
    )

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(real.verify_otp("01712345678", "1111"))

    assert exc_info.value.reason == "OTP_INCORRECT"
    assert exc_info.value.attempts_remaining == 2
    assert "2 attempt(s) remaining" in str(exc_info.value)


def test_verify_otp_400_without_parseable_attempts_remaining_leaves_it_none(monkeypatch):
    _install_request(
        monkeypatch,
        response=FakeResponse(status_code=400, json_data={"message": "Validation failed"}),
    )

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(real.verify_otp("01712345678", "abcd"))

    assert exc_info.value.reason == "OTP_INCORRECT"
    assert exc_info.value.attempts_remaining is None


def test_verify_otp_410_raises_adapter_validation_error_otp_expired(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(status_code=410, json_data={}))

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(real.verify_otp("01712345678", "0000"))

    assert exc_info.value.reason == "OTP_EXPIRED"


def test_verify_otp_429_raises_adapter_validation_error_otp_blocked(monkeypatch):
    _install_request(
        monkeypatch,
        response=FakeResponse(status_code=429, json_data={"message": "Phone blocked for 5 minutes"}),
    )

    with pytest.raises(AdapterValidationError) as exc_info:
        asyncio.run(real.verify_otp("01712345678", "0000"))

    assert exc_info.value.reason == "OTP_BLOCKED"


def test_verify_otp_other_status_raises_adapter_unavailable_error(monkeypatch):
    _install_request(monkeypatch, response=FakeResponse(status_code=500))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.verify_otp("01712345678", "0000"))


def test_verify_otp_network_error_raises_adapter_unavailable_error_not_raw_httpx(monkeypatch):
    _install_request(monkeypatch, exception=httpx.ConnectError("connection refused"))

    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real.verify_otp("01712345678", "0000"))


def test_parse_attempts_remaining_matches_documented_pattern_case_insensitively():
    assert real._parse_attempts_remaining("Invalid OTP. 2 attempt(s) remaining.") == 2
    assert real._parse_attempts_remaining("invalid otp. 1 ATTEMPT(S) REMAINING.") == 1
    assert real._parse_attempts_remaining("no attempts info here") is None
