"""T-64: tests for the 17 read-only (GET) real adapters added to
app/banking/adapters/real.py. Same mocking style as tests/test_real_adapters.py
(httpx.AsyncClient.request monkeypatched; fulfill() driven with asyncio.run)."""
import asyncio

import httpx
import pytest

import app.banking.adapters.real as real
from app.banking.adapter_map import REAL_ADAPTER_SUBSERVICE_IDS, get_adapter_name
from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterUnavailableError,
)
from app.banking.identity import CustomerIdentity

_IDENTITY = CustomerIdentity(customer_id="cust-123")
_JWT = "test.jwt.token"

_ACCOUNTS_PATH = "/polygon-bank/v1/accounts"


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


def _install(monkeypatch, responder):
    """responder(method, path, params) -> FakeResponse. Returns captured calls."""
    calls = []

    async def fake_request(self, method, path, *, headers=None, params=None, json=None):
        calls.append(
            {"method": method, "path": path, "headers": headers, "params": params, "json": json}
        )
        return responder(method, path, params)

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    return calls


def _fixed(monkeypatch, response):
    return _install(monkeypatch, lambda m, p, q: response)


def _by_path(monkeypatch, mapping):
    return _install(monkeypatch, lambda m, p, q: mapping[p])


def _run(adapter, payload=None):
    return asyncio.run(adapter.fulfill(_IDENTITY, _JWT, "subservice", payload))


def _accounts_body(accounts):
    return {"data": {"accounts": accounts, "ledgerAccounts": []}, "status": "success"}


def _account(id_, number, cards=None):
    return {"id": id_, "accountNumber": number, "accountName": "Test", "accountType": "SAVINGS",
            "balance": "0.00", "cards": cards or []}


def _card(id_, card_type, number="4001****0001"):
    return {"id": id_, "cardType": card_type, "cardNumber": number, "status": "ACTIVE"}


# --- registration -----------------------------------------------------------

_T64 = {
    "my_tickets": "complaints_adapter",
    "account_transactions": "account_transactions_adapter",
    "card_limit_requests": "card_limit_requests_adapter",
    "card_products": "card_products_adapter",
    "virtual_card_requests": "virtual_card_requests_adapter",
    "replacement_requests": "replacement_requests_adapter",
    "credit_card_summary": "credit_card_summary_adapter",
    "credit_card_statement": "credit_card_statement_adapter",
    "profile": "profile_adapter",
    "address": "address_adapter",
    "contacts": "contacts_adapter",
    "profile_change_requests": "profile_change_requests_adapter",
    "contact_priority_requests": "contact_priority_requests_adapter",
    "gifts_received": "gifts_received_adapter",
    "email_transfers": "email_transfers_adapter",
    "qr_payment_history": "qr_payment_history_adapter",
    "transfer_limit": "transfer_limit_adapter",
}


@pytest.mark.parametrize("service_id,attr", sorted(_T64.items()))
def test_t64_adapter_registered_in_real_adapters_and_adapter_map(service_id, attr):
    assert real.REAL_ADAPTERS[f"real:{service_id}"] is getattr(real, attr)
    assert service_id in REAL_ADAPTER_SUBSERVICE_IDS
    assert get_adapter_name("any_category", service_id) == f"real:{service_id}"


# --- auth / failure mapping across every T-64 adapter -----------------------
# Payloads carry explicit ids so no account/card lookup is needed; the single
# HTTP call is the endpoint itself.

_EXPLICIT_PAYLOADS = {
    "account_transactions_adapter": {"id": "74"},
    "credit_card_summary_adapter": {"cardId": "9"},
    "credit_card_statement_adapter": {"cardId": "9", "isBilled": True, "month": "2026-09"},
    "transfer_limit_adapter": {"accountNumber": "100126000015"},
}


@pytest.mark.parametrize("attr", sorted(_T64.values()))
@pytest.mark.parametrize("status", [401, 403])
def test_t64_adapter_401_403_raises_adapter_auth_error(monkeypatch, attr, status):
    _fixed(monkeypatch, FakeResponse(status_code=status))
    with pytest.raises(AdapterAuthError):
        _run(getattr(real, attr), _EXPLICIT_PAYLOADS.get(attr, {}))


@pytest.mark.parametrize("attr", sorted(_T64.values()))
@pytest.mark.parametrize("status", [404, 422, 500])
def test_t64_adapter_non_auth_failure_raises_adapter_unavailable(monkeypatch, attr, status):
    _fixed(monkeypatch, FakeResponse(status_code=status))
    with pytest.raises(AdapterUnavailableError):
        _run(getattr(real, attr), _EXPLICIT_PAYLOADS.get(attr, {}))


@pytest.mark.parametrize("attr", sorted(_T64.values()))
def test_t64_adapter_network_error_raises_adapter_unavailable(monkeypatch, attr):
    async def boom(self, method, path, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "request", boom)
    with pytest.raises(AdapterUnavailableError):
        _run(getattr(real, attr), _EXPLICIT_PAYLOADS.get(attr, {}))


@pytest.mark.parametrize("attr", sorted(_T64.values()))
def test_t64_adapter_forwards_jwt_and_uses_get_only(monkeypatch, attr):
    calls = _fixed(monkeypatch, FakeResponse(json_data={"ok": True}))
    _run(getattr(real, attr), _EXPLICIT_PAYLOADS.get(attr, {}))
    assert calls
    for c in calls:
        assert c["method"] == "GET"
        assert c["json"] is None
        assert c["headers"] == {"Authorization": f"Bearer {_JWT}"}


@pytest.mark.parametrize("attr", sorted(_T64.values()))
def test_t64_adapter_result_is_always_a_dict_even_for_bare_array(monkeypatch, attr):
    _fixed(monkeypatch, FakeResponse(json_data=[{"id": 1}, {"id": 2}]))
    result = _run(getattr(real, attr), _EXPLICIT_PAYLOADS.get(attr, {}))
    assert isinstance(result.data, dict)
    (only_value,) = result.data.values()
    assert only_value == [{"id": 1}, {"id": 2}]


# --- simple GETs: path, no params, bare-array key ---------------------------

@pytest.mark.parametrize(
    "attr,path,list_key",
    [
        ("complaints_adapter", "/support/v1/complaints", "complaints"),
        ("card_limit_requests_adapter", "/card/v1/cards/limit-change-requests", "requests"),
        ("replacement_requests_adapter", "/card/v1/cards/replacement-requests", "requests"),
        ("profile_adapter", "/auth/v1/user", "profile"),
        ("address_adapter", "/customer/v1/me/demographic", "address"),
        ("contacts_adapter", "/customer/v1/me/contacts", "contacts"),
        ("profile_change_requests_adapter", "/service-request/v1/profile-changes", "requests"),
        ("contact_priority_requests_adapter", "/service-request/v1/contact-priority", "requests"),
        ("gifts_received_adapter", "/transfer/v1/bank-transfer/gift/received", "items"),
    ],
)
def test_simple_get_adapter_path_params_and_bare_array_wrap(monkeypatch, attr, path, list_key):
    calls = _fixed(monkeypatch, FakeResponse(json_data=[{"id": 3}]))
    result = _run(getattr(real, attr), {"irrelevant": "x"})
    assert len(calls) == 1
    assert calls[0]["path"] == path
    assert calls[0]["params"] is None
    assert result.data == {list_key: [{"id": 3}]}


def test_simple_get_adapter_dict_body_returned_unchanged(monkeypatch):
    body = {"status": "success", "data": {"district": "Dhaka"}}
    _fixed(monkeypatch, FakeResponse(json_data=body))
    assert _run(real.address_adapter).data == body


# --- paged GETs -------------------------------------------------------------

@pytest.mark.parametrize(
    "attr,path,default_size,list_key",
    [
        ("virtual_card_requests_adapter", "/card/v1/cards/virtual/requests", 10, "requests"),
        ("qr_payment_history_adapter", "/merchant/v1/qr/history", 20, "payments"),
    ],
)
def test_paged_adapter_defaults_and_payload_override(monkeypatch, attr, path, default_size, list_key):
    calls = _fixed(monkeypatch, FakeResponse(json_data=[]))
    result = _run(getattr(real, attr), None)
    assert calls[0]["path"] == path
    assert calls[0]["params"] == {"page": 0, "size": default_size}
    assert result.data == {list_key: []}

    calls = _fixed(monkeypatch, FakeResponse(json_data={"data": []}))
    _run(getattr(real, attr), {"page": 2, "size": 5})
    assert calls[0]["params"] == {"page": 2, "size": 5}


# --- card products ----------------------------------------------------------

def test_card_products_no_filters_sends_no_params(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data={"data": [], "status": "success"}))
    _run(real.card_products_adapter, {"unrelated": 1})
    assert calls[0]["path"] == "/card/v1/card-products"
    assert calls[0]["params"] is None


def test_card_products_forwards_only_present_documented_filters(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data={"data": []}))
    _run(real.card_products_adapter, {"cardCategory": "CREDIT", "scheme": "VISA", "bogus": "x"})
    assert calls[0]["params"] == {"cardCategory": "CREDIT", "scheme": "VISA"}


# --- account transactions ---------------------------------------------------

_TXN_BODY = {"data": {"transactions": [{"amount": 1}]}, "status": "success"}


def test_account_transactions_explicit_id_skips_lookup(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data=_TXN_BODY))
    result = _run(real.account_transactions_adapter, {"id": "74"})
    assert [c["path"] for c in calls] == ["/polygon-bank/v1/accounts/74/transactions"]
    assert calls[0]["params"] is None
    assert result.data == _TXN_BODY


def test_account_transactions_single_account_auto_resolves_internal_id_not_number(monkeypatch):
    calls = _by_path(monkeypatch, {
        _ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body([_account("74", "100126000015")])),
        "/polygon-bank/v1/accounts/74/transactions": FakeResponse(json_data=_TXN_BODY),
    })
    _run(real.account_transactions_adapter)
    assert [c["path"] for c in calls] == [_ACCOUNTS_PATH, "/polygon-bank/v1/accounts/74/transactions"]


def test_account_transactions_zero_accounts_raises_unavailable(monkeypatch):
    calls = _by_path(monkeypatch, {_ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body([]))})
    with pytest.raises(AdapterUnavailableError):
        _run(real.account_transactions_adapter)
    assert len(calls) == 1


def test_account_transactions_multiple_accounts_raises_selection_with_ids(monkeypatch):
    _by_path(monkeypatch, {_ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body(
        [_account("74", "111"), _account("75", "222")]
    ))})
    with pytest.raises(AdapterAccountSelectionRequiredError) as exc_info:
        _run(real.account_transactions_adapter)
    accounts = exc_info.value.accounts
    assert [(a["id"], a["accountNumber"]) for a in accounts] == [("74", "111"), ("75", "222")]
    assert all("cards" not in a for a in accounts)


def test_account_transactions_account_number_maps_to_internal_id(monkeypatch):
    calls = _by_path(monkeypatch, {
        _ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body(
            [_account("74", "111"), _account("75", "222")]
        )),
        "/polygon-bank/v1/accounts/75/transactions": FakeResponse(json_data=_TXN_BODY),
    })
    _run(real.account_transactions_adapter, {"accountNumber": "222"})
    assert calls[-1]["path"] == "/polygon-bank/v1/accounts/75/transactions"


def test_account_transactions_unknown_account_number_raises_unavailable(monkeypatch):
    _by_path(monkeypatch, {_ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body([_account("74", "111")]))})
    with pytest.raises(AdapterUnavailableError):
        _run(real.account_transactions_adapter, {"accountNumber": "999"})


def test_account_transactions_accounts_lookup_401_raises_auth(monkeypatch):
    _by_path(monkeypatch, {_ACCOUNTS_PATH: FakeResponse(status_code=401)})
    with pytest.raises(AdapterAuthError):
        _run(real.account_transactions_adapter)


# --- credit card resolution (summary + statement) ---------------------------

_SUMMARY_BODY = {"data": {"creditLimit": 100}, "status": "success"}


def test_credit_summary_explicit_card_id_skips_lookup(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data=_SUMMARY_BODY))
    result = _run(real.credit_card_summary_adapter, {"cardId": "9"})
    assert [c["path"] for c in calls] == ["/card/v1/cards/9/credit-summary"]
    assert result.data == _SUMMARY_BODY


_CARDS_PATH = "/card/v1/cards"


def _cards_body(*cards):
    return {"status": "success", "data": list(cards)}


def _full_card(card_id, category, number):
    return {"id": card_id, "cardCategory": category, "cardType": "PHYSICAL",
            "cardNumber": number, "status": "ACTIVE"}


@pytest.mark.parametrize("attr", ["credit_card_summary_adapter", "credit_card_statement_adapter"])
def test_credit_card_zero_credit_cards_answers_no_credit_card(monkeypatch, attr):
    calls = _by_path(monkeypatch, {_CARDS_PATH: FakeResponse(json_data=_cards_body(
        _full_card("41", "DEBIT", "4001230000000251")))})
    result = _run(getattr(real, attr))
    assert result.data == {"creditCards": [], "hasCreditCard": False}
    assert [c["path"] for c in calls] == [_CARDS_PATH]


def test_credit_summary_resolves_via_card_list_not_accounts(monkeypatch):
    calls = _by_path(monkeypatch, {
        _CARDS_PATH: FakeResponse(json_data=_cards_body(
            _full_card("41", "DEBIT", "4001230000000251"),
            _full_card("99", "CREDIT", "4100200000000379"))),
        "/card/v1/cards/99/credit-summary": FakeResponse(json_data=_SUMMARY_BODY),
    })
    _run(real.credit_card_summary_adapter)
    assert [c["path"] for c in calls] == [_CARDS_PATH, "/card/v1/cards/99/credit-summary"]


@pytest.mark.parametrize("attr", ["credit_card_summary_adapter", "credit_card_statement_adapter"])
def test_credit_card_multiple_credit_cards_selection_masks_full_numbers(monkeypatch, attr):
    _by_path(monkeypatch, {_CARDS_PATH: FakeResponse(json_data=_cards_body(
        _full_card("98", "CREDIT", "4100200000000001"),
        _full_card("99", "CREDIT", "4100200000000002")))})
    with pytest.raises(AdapterAccountSelectionRequiredError) as exc_info:
        _run(getattr(real, attr))
    assert exc_info.value.accounts == [
        {"id": "98", "cardNumber": "****0001", "cardType": "CREDIT", "status": "ACTIVE"},
        {"id": "99", "cardNumber": "****0002", "cardType": "CREDIT", "status": "ACTIVE"},
    ]
    assert "4100200000000001" not in str(exc_info.value.accounts)


def test_credit_statement_forwards_is_billed_and_month_when_present(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data={"data": {}}))
    _run(real.credit_card_statement_adapter, {"cardId": "9", "isBilled": True, "month": "2026-09"})
    assert calls[0]["path"] == "/card/v1/cards/9/statements"
    assert calls[0]["params"] == {"isBilled": "true", "month": "2026-09"}


def test_credit_statement_defaults_to_current_month_unbilled(monkeypatch):
    from datetime import datetime, timezone
    calls = _fixed(monkeypatch, FakeResponse(json_data={"data": {}}))
    _run(real.credit_card_statement_adapter, {"cardId": "9"})
    assert calls[0]["params"] == {
        "isBilled": "false", "month": datetime.now(timezone.utc).strftime("%Y-%m")}


# --- email transfers --------------------------------------------------------

def test_email_transfers_list_no_params_by_default(monkeypatch):
    body = {"items": [], "pagination": {"totalCount": 0}}
    calls = _fixed(monkeypatch, FakeResponse(json_data=body))
    result = _run(real.email_transfers_adapter, None)
    assert calls[0]["path"] == "/transfer/v1/email-transfer"
    assert calls[0]["params"] is None
    assert result.data == body


def test_email_transfers_list_forwards_tab_page_size_when_present(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data={"items": []}))
    _run(real.email_transfers_adapter, {"tab": "sent", "page": 1, "size": 5})
    assert calls[0]["params"] == {"tab": "sent", "page": 1, "size": 5}


def test_email_transfers_with_id_calls_detail_endpoint(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data={"id": 12}))
    result = _run(real.email_transfers_adapter, {"id": 12})
    assert [c["path"] for c in calls] == ["/transfer/v1/email-transfer/12"]
    assert calls[0]["params"] is None
    assert result.data == {"id": 12}


# --- transfer limit ---------------------------------------------------------

_LIMIT_BODY = {"accountIdentifier": "111", "daily": {"used": 0}}


def test_transfer_limit_explicit_account_number(monkeypatch):
    calls = _fixed(monkeypatch, FakeResponse(json_data=_LIMIT_BODY))
    result = _run(real.transfer_limit_adapter, {"accountNumber": "111"})
    assert [c["path"] for c in calls] == ["/transfer/v1/my-limit/111"]
    assert result.data == _LIMIT_BODY


def test_transfer_limit_single_account_auto_resolves_account_number(monkeypatch):
    calls = _by_path(monkeypatch, {
        _ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body([_account("74", "111")])),
        "/transfer/v1/my-limit/111": FakeResponse(json_data=_LIMIT_BODY),
    })
    _run(real.transfer_limit_adapter)
    assert calls[-1]["path"] == "/transfer/v1/my-limit/111"


def test_transfer_limit_zero_accounts_raises_unavailable(monkeypatch):
    _by_path(monkeypatch, {_ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body([]))})
    with pytest.raises(AdapterUnavailableError):
        _run(real.transfer_limit_adapter)


def test_transfer_limit_multiple_accounts_raises_selection(monkeypatch):
    _by_path(monkeypatch, {_ACCOUNTS_PATH: FakeResponse(json_data=_accounts_body(
        [_account("74", "111"), _account("75", "222")]
    ))})
    with pytest.raises(AdapterAccountSelectionRequiredError) as exc_info:
        _run(real.transfer_limit_adapter)
    assert [a["accountNumber"] for a in exc_info.value.accounts] == ["111", "222"]
