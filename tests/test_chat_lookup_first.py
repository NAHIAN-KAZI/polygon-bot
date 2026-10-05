"""Lookup-first gathering: "never ask the customer what the bank already knows".

Covers chat.py's _prefill_from_bank (dispute account/transaction, own-account transfer
destination), _carry_forward_gathered, the beneficiary-add recipient lookup, readable
bank refusals (AdapterRejectedError) in the yes/no and email/mobile OTP paths,
_accounts_for_prompt dropping card rows -- and real.py's lookup_recipient, _call's
status-code mapping, _resolve_credit_card_id's live response shape and card-row
exclusion in the account resolvers.

Nothing reaches the network: adapter tests replace real._call or httpx.AsyncClient.request;
chat tests replace classify / verify_jwt / fulfill_banking_service / lookup_recipient /
send_otp / verify_otp at their app.routes.chat import sites. Multi-turn flows use the
REAL in-memory session store (reset per test).
"""
import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

import app.banking.adapters.real as real_module
import app.banking.session as session_module
import app.routes.chat as chat_module
from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterRejectedError,
    AdapterResult,
    AdapterUnavailableError,
)
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification
from app.banking.session import ChatTurn

from tests.conftest import AUTH_HEADERS

CUSTOMER_PHONE = "01712345678"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
IDENTITY = CustomerIdentity(customer_id=CUSTOMER_PHONE)

SAVINGS = {"id": 11, "accountNumber": "2001000011112222", "accountType": "SAVINGS", "balance": 0}
CURRENT = {"id": 12, "accountNumber": "2001000033334444", "accountType": "CURRENT", "balance": 0}
CARD_ROW_BY_ID = {"id": "card-7", "accountNumber": "4001230000009999", "accountType": "DEBIT", "balance": "0"}
CARD_ROW_BY_TYPE = {"id": 99, "accountNumber": "5001230000008888", "accountType": "credit", "balance": "0"}
PREPAID_ROW = {"id": 98, "accountNumber": "5001230000007777", "accountType": "PREPAID", "balance": "0"}

TXNS = [
    {"transactionId": "TXN-A", "txnTime": "2026-10-01T09:00:00", "type": "DEBIT", "amount": 500,
     "transactionType": "ATM", "accountNumber": SAVINGS["accountNumber"], "balanceAfter": 1000},
    {"transactionId": "TXN-B", "txnTime": "2026-10-02T10:30:00", "type": "DEBIT", "amount": 2000,
     "transactionType": "NPSB", "accountNumber": SAVINGS["accountNumber"]},
    {"txnTime": "2026-10-03T10:30:00", "amount": 1},  # no transactionId: never offered
]


# --- SSE helpers --------------------------------------------------------------


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


def _result(events):
    return next(data for name, data in events if name == "result")


def _token(events):
    return "".join(data["token"] for name, data in events if name == "token")


def _post(client, message, payload=None, **extra):
    body = {"message": message, **extra}
    if payload is not None:
        body["payload"] = payload
    resp = client.post("/chat", json=body, headers=JWT_HEADERS)
    assert resp.status_code == 200
    return _parse_sse(resp.text)


# --- fake bank ------------------------------------------------------------------


class FakeBank:
    def __init__(self):
        self.accounts: list[dict] = [SAVINGS, CARD_ROW_BY_ID]
        self.transactions: list[dict] = list(TXNS)
        self.fulfills: list[tuple[str, str, dict | None]] = []
        self.fulfill_errors: dict[tuple[str, str], Exception] = {}
        self.routes: dict[str, object] = {}
        self.classify_calls: list[str] = []
        self.picks: list[tuple[str, list[dict]]] = []
        self.pick_index: int | None = None
        self.recipient: dict | None | Exception = None
        self.lookups: list[str] = []
        self.sends: list[str] = []

    async def fulfill(self, customer_identity, jwt, category, service, subservice, payload):
        self.fulfills.append((category, service, dict(payload) if payload else payload))
        error = self.fulfill_errors.get((category, service))
        if error is not None:
            raise error
        if (category, service) == ("account_info", "accounts"):
            return AdapterResult(data={"data": {"accounts": self.accounts}})
        if (category, service) == ("polygon_services", "transaction_history"):
            return AdapterResult(data={"transactions": self.transactions})
        return AdapterResult(data={"success": True})

    def lookups_of(self, category, service):
        return [f for f in self.fulfills if (f[0], f[1]) == (category, service)]

    async def pick(self, message, candidates):
        self.picks.append((message, candidates))
        return self.pick_index

    async def lookup_recipient(self, jwt, identifier):
        self.lookups.append(identifier)
        if isinstance(self.recipient, Exception):
            raise self.recipient
        return self.recipient

    async def classify(self, message, recent_turns=None):
        self.classify_calls.append(message)
        for needle, result in self.routes.items():
            if needle in message.lower():
                return result
        return Clarification(question="What would you like to do?")

    async def send_otp(self, phone):
        self.sends.append(phone)

    async def verify_otp(self, phone, otp):
        return "vtoken-1"


@pytest.fixture
def bank(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})
    fake = FakeBank()

    async def fake_verify_jwt(token):
        return IDENTITY

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake.classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake.fulfill)
    monkeypatch.setattr(chat_module, "_llm_pick_candidate", fake.pick)
    monkeypatch.setattr(chat_module, "lookup_recipient", fake.lookup_recipient)
    monkeypatch.setattr(chat_module, "send_otp", fake.send_otp)
    monkeypatch.setattr(chat_module, "verify_otp", fake.verify_otp)
    return fake


def _prefill(category, service, subservice, payload, context="my ATM didn't give cash"):
    return asyncio.run(chat_module._prefill_from_bank(
        IDENTITY, "jwt-x", category, service, subservice, payload, context))


def _dispute(payload, context="my ATM didn't give cash"):
    return _prefill("service_requests", "raise_dispute", None, payload, context)


# --- _prefill_from_bank: dispute account -----------------------------------------


def test_dispute_single_deposit_account_is_filled_and_card_rows_ignored(bank):
    bank.accounts = [CARD_ROW_BY_ID, SAVINGS, CARD_ROW_BY_TYPE, PREPAID_ROW]
    bank.pick_index = 0
    payload, outcome = _dispute({"remarks": "no cash"})
    assert outcome is None
    assert payload["accountNumber"] == SAVINGS["accountNumber"]
    # Then the account's recent transactions are looked up with that account.
    assert bank.lookups_of("polygon_services", "transaction_history") == [
        ("polygon_services", "transaction_history",
         {"accountNumber": SAVINGS["accountNumber"], "size": 8}),
    ]


def test_dispute_two_deposit_accounts_asks_which(bank):
    bank.accounts = [SAVINGS, CARD_ROW_BY_ID, CURRENT]
    payload, outcome = _dispute({"remarks": "no cash"})
    assert outcome is not None
    assert outcome.result_type == "ACCOUNT_SELECTION_REQUIRED"
    assert outcome.result_payload == {"accounts": [SAVINGS, CURRENT]}
    stored = outcome.classification()
    assert stored["candidates"] == [SAVINGS, CURRENT]
    assert stored["payload"] == {"remarks": "no cash"}
    assert (stored["category"], stored["service"]) == ("service_requests", "raise_dispute")
    # No transaction lookup before the account is known.
    assert bank.lookups_of("polygon_services", "transaction_history") == []


def test_dispute_no_deposit_account_falls_back_to_asking(bank):
    bank.accounts = [CARD_ROW_BY_ID]
    payload, outcome = _dispute({"remarks": "no cash"})
    assert outcome is None
    assert "accountNumber" not in payload
    assert bank.lookups_of("polygon_services", "transaction_history") == []


# --- _prefill_from_bank: dispute transaction -------------------------------------


def test_dispute_transaction_picked_by_model_fills_reference_and_summary(bank):
    bank.pick_index = 1
    payload, outcome = _dispute({"accountNumber": SAVINGS["accountNumber"], "remarks": "wrong amount"},
                                context="the NPSB transfer yesterday")
    assert outcome is None
    assert payload["transactionReferenceNo"] == "TXN-B"
    expected_choice = chat_module._transaction_choice(TXNS[1])
    assert payload["transactionSummary"] == chat_module._describe_selection_account(expected_choice)
    # No account lookup when the account was already known.
    assert bank.lookups_of("account_info", "accounts") == []
    # The model sees the context + remarks, and choices without any account number.
    (message, choices), = bank.picks
    assert "the NPSB transfer yesterday" in message and "wrong amount" in message
    assert [c["transactionId"] for c in choices] == ["TXN-A", "TXN-B"]
    assert all("accountNumber" not in c and "balanceAfter" not in c for c in choices)


def test_dispute_transaction_no_clear_match_asks_customer_to_pick(bank):
    bank.pick_index = None
    payload, outcome = _dispute({"accountNumber": SAVINGS["accountNumber"], "remarks": "wrong amount"})
    assert "transactionReferenceNo" not in payload
    assert outcome.result_type == "TRANSACTION_SELECTION_REQUIRED"
    transactions = outcome.result_payload["transactions"]
    assert [t["transactionId"] for t in transactions] == ["TXN-A", "TXN-B"]
    assert all("accountNumber" not in t for t in transactions)
    stored = outcome.classification()
    assert stored["candidates"] == transactions
    assert stored["payload"]["accountNumber"] == SAVINGS["accountNumber"]
    assert outcome.token.startswith("Which transaction is this about?")


def test_dispute_without_transactions_falls_back_to_asking(bank):
    bank.transactions = []
    payload, outcome = _dispute({"accountNumber": SAVINGS["accountNumber"]})
    assert outcome is None
    assert "transactionReferenceNo" not in payload
    assert bank.picks == []


def test_dispute_with_reference_already_known_does_no_lookup(bank):
    given = {"accountNumber": SAVINGS["accountNumber"], "transactionReferenceNo": "REF1"}
    payload, outcome = _dispute(given)
    assert outcome is None and payload == given
    assert bank.fulfills == []


def test_prefill_auth_error_requires_login(bank):
    bank.fulfill_errors[("account_info", "accounts")] = AdapterAuthError("expired")
    _, outcome = _dispute({"remarks": "x"})
    assert outcome.result_type == "AUTH_REQUIRED"


def test_prefill_unavailable_falls_back_to_asking(bank):
    bank.fulfill_errors[("polygon_services", "transaction_history")] = AdapterUnavailableError("down")
    payload, outcome = _dispute({"accountNumber": SAVINGS["accountNumber"]})
    assert outcome is None
    assert payload == {"accountNumber": SAVINGS["accountNumber"]}


# --- _prefill_from_bank: own-account transfer / other services -------------------


@pytest.mark.parametrize("accounts", [[SAVINGS], [SAVINGS, CARD_ROW_BY_ID, CARD_ROW_BY_TYPE], []])
def test_own_account_transfer_with_one_account_explains_and_does_not_execute(bank, accounts):
    bank.accounts = accounts
    _, outcome = _prefill("transfer", "bank_transfer", "own_account", {"amount": 500})
    assert outcome.result_type == "BANKING_SERVICE"
    assert outcome.result_payload == {"executed": False}
    assert "only one account" in outcome.token


def test_own_account_transfer_with_two_accounts_asks_which(bank):
    bank.accounts = [SAVINGS, CARD_ROW_BY_ID, CURRENT]
    _, outcome = _prefill("transfer", "bank_transfer", "own_account", {"amount": 500})
    assert outcome.result_type == "ACCOUNT_SELECTION_REQUIRED"
    assert outcome.result_payload == {"accounts": [SAVINGS, CURRENT]}
    assert outcome.classification()["subservice"] == "own_account"


def test_own_account_transfer_with_destination_known_does_no_lookup(bank):
    payload, outcome = _prefill("transfer", "bank_transfer", "own_account",
                                {"accountNumber": CURRENT["accountNumber"]})
    assert outcome is None and bank.fulfills == []


@pytest.mark.parametrize("category,service,subservice", [
    ("transfer", "bank_transfer", "other_bank"),
    ("account_info", "balance", None),
    ("beneficiary_management", "beneficiary_add", None),
])
def test_prefill_leaves_other_services_untouched(bank, category, service, subservice):
    payload, outcome = _prefill(category, service, subservice, {"x": "y"})
    assert payload == {"x": "y"} and outcome is None
    assert bank.fulfills == []


# --- /chat end-to-end: dispute ---------------------------------------------------


def test_chat_dispute_picks_transaction_and_summarises_with_masked_account(client, bank):
    bank.pick_index = 0
    bank.routes["dispute"] = BankingService(
        "service_requests", "raise_dispute", None, {"remarks": "ATM did not give cash"})
    events = _post(client, "I want to dispute the ATM withdrawal")
    result = _result(events)
    token = _token(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["routing"]["action"] == "raise_dispute"
    assert result["payload"]["transactionReferenceNo"] == "TXN-A"
    assert result["payload"]["executed"] is False
    summary = chat_module._describe_selection_account(chat_module._transaction_choice(TXNS[0]))
    assert summary in token
    assert "ending 2222" in token
    assert SAVINGS["accountNumber"] not in token
    # Read-only lookups only; never a dispute submission.
    assert [(c, s) for c, s, _ in bank.fulfills] == [
        ("account_info", "accounts"), ("polygon_services", "transaction_history")]


def test_chat_dispute_transaction_pick_from_frontend_resumes(client, bank):
    bank.pick_index = None
    bank.routes["dispute"] = BankingService(
        "service_requests", "raise_dispute", None, {"remarks": "charged twice"})
    events = _post(client, "I want to dispute a charge")
    first = _result(events)
    assert first["type"] == "TRANSACTION_SELECTION_REQUIRED"
    assert [t["transactionId"] for t in first["payload"]["transactions"]] == ["TXN-A", "TXN-B"]

    events = _post(client, "this one", {"transactionId": "TXN-B"})
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"]["transactionReferenceNo"] == "TXN-B"
    assert result["payload"]["accountNumber"] == SAVINGS["accountNumber"]
    assert result["payload"]["remarks"] == "charged twice"
    summary = chat_module._describe_selection_account(chat_module._transaction_choice(TXNS[1]))
    assert summary in _token(events)
    # Resumed from the stored pick, not re-classified, no second history fetch.
    assert bank.classify_calls == ["I want to dispute a charge"]
    assert len(bank.lookups_of("polygon_services", "transaction_history")) == 1


def test_chat_dispute_with_two_accounts_asks_which_account(client, bank):
    bank.accounts = [SAVINGS, CURRENT, CARD_ROW_BY_ID]
    bank.routes["dispute"] = BankingService("service_requests", "raise_dispute", None, {"remarks": "x"})
    events = _post(client, "dispute a transaction")
    result = _result(events)
    assert result["type"] == "ACCOUNT_SELECTION_REQUIRED"
    assert result["payload"] == {"accounts": [SAVINGS, CURRENT]}


# --- _carry_forward_gathered -----------------------------------------------------


def _turn(classification):
    return ChatTurn(timestamp=datetime.now(timezone.utc), message="earlier", classification=classification)


def _clar_turn(category="beneficiary_management", service="beneficiary_add", payload=None, type_="CLARIFICATION_REQUIRED"):
    return _turn({"type": type_, "category": category, "service": service, "subservice": None,
                  "payload": payload})


def test_carry_forward_merges_stored_answers_new_values_win():
    result = BankingService("beneficiary_management", "beneficiary_add", None,
                            {"accountNumber": "123456789", "nickname": "Mom"})
    turns = [_clar_turn(payload={"nickname": "Rafi", "bankName": "", "branchName": None, "routingNumber": "0123"})]
    merged = chat_module._carry_forward_gathered(result, turns)
    assert merged.payload == {"nickname": "Mom", "accountNumber": "123456789", "routingNumber": "0123"}
    assert (merged.category, merged.service) == ("beneficiary_management", "beneficiary_add")


def test_carry_forward_with_no_new_payload_keeps_stored():
    result = BankingService("beneficiary_management", "beneficiary_add", None, None)
    merged = chat_module._carry_forward_gathered(result, [_clar_turn(payload={"nickname": "Rafi"})])
    assert merged.payload == {"nickname": "Rafi"}


@pytest.mark.parametrize("turns", [
    [_clar_turn(service="beneficiary_list", payload={"nickname": "Rafi"})],
    [_clar_turn(payload={"nickname": "Rafi"}, type_="BANKING_SERVICE")],
    [_clar_turn(payload={"nickname": "Rafi"}, type_="CONFIRMATION_REQUIRED")],
    [_clar_turn(payload={"nickname": "", "bankName": None})],
    [_clar_turn(payload={"nickname": "Rafi"}), _turn({"type": "KB_QUESTION"})],
    [],
])
def test_carry_forward_leaves_result_unchanged(turns):
    result = BankingService("beneficiary_management", "beneficiary_add", None, {"accountNumber": "1"})
    assert chat_module._carry_forward_gathered(result, turns) is result


def test_carry_forward_ignores_non_banking_results():
    clar = Clarification(question="?")
    assert chat_module._carry_forward_gathered(clar, [_clar_turn(payload={"nickname": "R"})]) is clar


# --- beneficiary add: recipient lookup -------------------------------------------


BEN_ROUTE = BankingService("beneficiary_management", "beneficiary_add", None,
                           {"nickname": "Rafi", "accountNumber": "2001000055556666"})


def test_beneficiary_add_polygon_account_confirms_with_holder_name(client, bank):
    bank.recipient = {"accountNumber": "2001000055556666", "accountName": "Rafiul Islam"}
    bank.routes["beneficiary"] = BEN_ROUTE
    events = _post(client, "add a beneficiary")
    result = _result(events)
    assert bank.lookups == ["2001000055556666"]
    assert result["type"] == "CONFIRMATION_REQUIRED"
    assert result["payload"]["serviceType"] == "OWN_BANK"
    assert result["payload"]["identifierType"] == "ACCOUNT"
    assert result["payload"]["accountHolderName"] == "Rafiul Islam"
    assert "Rafiul Islam's Polygon Bank account ending 6666" in _token(events)
    assert bank.fulfills == []

    _post(client, "yes")
    (call,) = bank.fulfills
    assert call[:2] == ("beneficiary_management", "beneficiary_add")
    assert call[2]["serviceType"] == "OWN_BANK"


def test_beneficiary_add_other_bank_asks_for_bank_details(client, bank):
    bank.recipient = None
    bank.routes["beneficiary"] = BEN_ROUTE
    events = _post(client, "add a beneficiary")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    stored = session_module.get_session(CUSTOMER_PHONE)[-1].classification
    assert stored["payload"]["serviceType"] == "OTHER_BANK"
    assert stored["missingFields"] == ["bankName", "branchName", "routingNumber"]
    assert bank.fulfills == []


def test_other_bank_missing_fields_rule():
    payload = {"serviceType": "OTHER_BANK", "nickname": "R", "accountNumber": "1"}
    assert chat_module._missing_payload_fields("beneficiary_management", "beneficiary_add", payload) == [
        "bankName", "branchName", "routingNumber"]
    full = {**payload, "bankName": "B", "branchName": "Br", "routingNumber": "0123"}
    assert chat_module._missing_payload_fields("beneficiary_management", "beneficiary_add", full) == []


def test_beneficiary_add_lookup_unavailable(client, bank):
    bank.recipient = AdapterUnavailableError("down")
    bank.routes["beneficiary"] = BEN_ROUTE
    events = _post(client, "add a beneficiary")
    assert _result(events)["type"] == "SERVICE_UNAVAILABLE"
    assert bank.fulfills == []


def test_beneficiary_add_with_service_type_known_skips_lookup(client, bank):
    bank.routes["beneficiary"] = BankingService(
        "beneficiary_management", "beneficiary_add", None,
        {"nickname": "Rafi", "accountNumber": "2001000055556666", "serviceType": "OWN_BANK"})
    events = _post(client, "add a beneficiary")
    assert bank.lookups == []
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"


# --- readable bank refusals in chat ------------------------------------------------


def test_confirmation_yes_rejected_by_bank_shows_its_message(client, bank):
    bank.routes["nickname"] = BankingService("profile_update", "update_nickname", None, {"nickName": "Rafi"})
    _post(client, "change my nickname")
    bank.fulfill_errors[("profile_update", "update_nickname")] = AdapterRejectedError(
        "PATCH ... returned 409: Nickname already taken.", "Nickname already taken.")
    events = _post(client, "yes")
    assert _token(events) == (
        "The bank reported a problem: Nickname already taken. Please check in the app whether "
        "the change was saved.")
    assert _result(events)["type"] == "SERVICE_UNAVAILABLE"


def test_email_change_rejected_after_otp_reports_bank_message(client, bank):
    bank.routes["email"] = BankingService("profile_update", "update_email", None, {"newEmail": "a@b.com"})
    assert _result(_post(client, "change my email"))["type"] == "OTP_REQUIRED"
    bank.fulfill_errors[("profile_update", "update_email")] = AdapterRejectedError(
        "POST ... returned 409: Email already in use.", "Email already in use.")
    events = _post(client, "submit", {"otp": "123456"})
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"] == {"executed": False, "bankMessage": "Email already in use."}
    assert "Email already in use." in _token(events)
    assert "Nothing has been changed." in _token(events)


def test_mobile_change_rejected_after_otp_reports_bank_message(client, bank):
    bank.routes["mobile"] = BankingService("profile_update", "update_mobile", None, {"newPhone": "01898765432"})
    assert _result(_post(client, "change my mobile"))["type"] == "OTP_REQUIRED"
    bank.fulfill_errors[("profile_update", "update_mobile")] = AdapterRejectedError(
        "x", "Invalid verification token")
    events = _post(client, "submit", {"otp": "123456"})
    assert _result(events)["payload"] == {"executed": False, "bankMessage": "Invalid verification token"}


# --- _accounts_for_prompt -----------------------------------------------------------


def test_accounts_for_prompt_drops_card_rows():
    data = {"data": {
        "accounts": [SAVINGS, CARD_ROW_BY_ID, CARD_ROW_BY_TYPE, PREPAID_ROW],
        "ledgerAccounts": [{"identifier": SAVINGS["accountNumber"], "balance": 90000}],
    }}
    view = chat_module._accounts_for_prompt(data)
    accounts = view["data"]["accounts"]
    assert [a["accountNumber"] for a in accounts] == [SAVINGS["accountNumber"]]
    assert accounts[0]["balance"] == 90000
    # Frontend payload untouched.
    assert len(data["data"]["accounts"]) == 4


# --- real.py: _is_card_row and account resolvers -------------------------------------


@pytest.mark.parametrize("row,expected", [
    ({"id": "card-1"}, True),
    ({"id": 5, "accountType": "CREDIT"}, True),
    ({"id": 5, "accountType": "prepaid"}, True),
    ({"id": 5, "accountType": "SAVINGS"}, False),
    ({"id": "acc-1", "accountType": "CURRENT"}, False),
    ({}, False),
    ("card-1", False),
    (None, False),
])
def test_is_card_row(row, expected):
    assert real_module._is_card_row(row) is expected


@pytest.fixture
def accounts_body(monkeypatch):
    holder = {"accounts": []}

    async def fake_call(method, path, jwt, *, params=None, json=None):
        assert (method, path) == ("GET", "/polygon-bank/v1/accounts")
        return {"data": {"accounts": holder["accounts"]}}

    monkeypatch.setattr(real_module, "_call", fake_call)
    return holder


def test_resolve_account_number_ignores_card_rows(accounts_body):
    accounts_body["accounts"] = [CARD_ROW_BY_ID, SAVINGS, CARD_ROW_BY_TYPE]
    number = asyncio.run(real_module._resolve_account_number(IDENTITY, "jwt", {}))
    assert number == SAVINGS["accountNumber"]


def test_resolve_account_number_only_cards_means_no_accounts(accounts_body):
    accounts_body["accounts"] = [CARD_ROW_BY_ID, PREPAID_ROW]
    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real_module._resolve_account_number(IDENTITY, "jwt", {}))


def test_resolve_account_number_selection_offers_only_deposit_accounts(accounts_body):
    accounts_body["accounts"] = [SAVINGS, CARD_ROW_BY_ID, CURRENT]
    with pytest.raises(AdapterAccountSelectionRequiredError) as excinfo:
        asyncio.run(real_module._resolve_account_number(IDENTITY, "jwt", {}))
    numbers = {a.get("accountNumber") for a in excinfo.value.accounts}
    assert numbers == {SAVINGS["accountNumber"], CURRENT["accountNumber"]}


def test_list_customer_accounts_excludes_card_rows(accounts_body):
    accounts_body["accounts"] = [SAVINGS, CARD_ROW_BY_ID, CURRENT, PREPAID_ROW]
    assert asyncio.run(real_module._list_customer_accounts(IDENTITY, "jwt")) == [SAVINGS, CURRENT]


# --- real.py: _resolve_credit_card_id live shape --------------------------------------


def test_resolve_credit_card_id_reads_live_data_cards_shape(monkeypatch):
    async def fake_call(method, path, jwt, *, params=None, json=None):
        assert (method, path) == ("GET", "/card/v1/cards")
        return {"status": "success", "data": {"cards": [
            {"id": 3, "cardNumber": "4001230000000001", "cardCategory": "DEBIT", "cardType": "PHYSICAL"},
            {"id": 77, "cardNumber": "5001230000000077", "cardCategory": "CREDIT", "cardType": "VIRTUAL"},
        ]}}

    monkeypatch.setattr(real_module, "_call", fake_call)
    assert asyncio.run(real_module._resolve_credit_card_id(IDENTITY, "jwt", {})) == "77"


def test_resolve_credit_card_id_still_reads_flat_list_shape(monkeypatch):
    async def fake_call(method, path, jwt, *, params=None, json=None):
        return {"data": [{"id": 8, "cardCategory": "CREDIT"}]}

    monkeypatch.setattr(real_module, "_call", fake_call)
    assert asyncio.run(real_module._resolve_credit_card_id(IDENTITY, "jwt", {})) == "8"


# --- real.py: lookup_recipient --------------------------------------------------------


def _install_call(monkeypatch, *, body=None, error=None):
    calls = []

    async def fake_call(method, path, jwt, *, params=None, json=None):
        calls.append((method, path, jwt))
        if error is not None:
            raise error
        return body

    monkeypatch.setattr(real_module, "_call", fake_call)
    return calls


def test_lookup_recipient_gets_digits_path_and_returns_data(monkeypatch):
    data = {"accountNumber": "2001000055556666", "accountName": "Rafiul Islam"}
    calls = _install_call(monkeypatch, body={"status": "success", "data": data})
    assert asyncio.run(real_module.lookup_recipient("jwt-x", "2001-0000 5555 6666")) == data
    assert calls == [("GET", "/polygon-bank/v1/accounts/recipient/2001000055556666", "jwt-x")]


@pytest.mark.parametrize("error", [
    AdapterUnavailableError("GET /polygon-bank/v1/accounts/recipient/1 returned 404: not found"),
    AdapterRejectedError("GET ... returned 400: bad", "Invalid identifier"),
])
def test_lookup_recipient_not_found_or_rejected_is_none(monkeypatch, error):
    _install_call(monkeypatch, error=error)
    assert asyncio.run(real_module.lookup_recipient("jwt", "12345")) is None


def test_lookup_recipient_other_failures_propagate(monkeypatch):
    _install_call(monkeypatch, error=AdapterUnavailableError("GET x returned 500: boom"))
    with pytest.raises(AdapterUnavailableError):
        asyncio.run(real_module.lookup_recipient("jwt", "12345"))


def test_lookup_recipient_without_digits_never_calls(monkeypatch):
    calls = _install_call(monkeypatch, body={})
    assert asyncio.run(real_module.lookup_recipient("jwt", "abc")) is None
    assert calls == []


def test_lookup_recipient_data_without_account_number_is_none(monkeypatch):
    _install_call(monkeypatch, body={"data": {"accountName": "X"}})
    assert asyncio.run(real_module.lookup_recipient("jwt", "12345")) is None


# --- real.py: _call status mapping -----------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="error"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._json_data is None:
            raise ValueError("not json")
        return self._json_data


def _install_response(monkeypatch, response):
    async def fake_request(self, method, path, *, headers=None, params=None, json=None):
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)


def _do_call():
    return asyncio.run(real_module._call("POST", "/auth/v1/auth/mobile/update", "jwt", json={}))


@pytest.mark.parametrize("status", [400, 409, 422, 428])
def test_call_readable_refusal_is_rejected_error(monkeypatch, status):
    _install_response(monkeypatch, FakeResponse(status, {"message": "Phone already in use"}))
    with pytest.raises(AdapterRejectedError) as excinfo:
        _do_call()
    assert excinfo.value.bank_message == "Phone already in use"
    assert isinstance(excinfo.value, AdapterUnavailableError)


@pytest.mark.parametrize("status", [400, 409])
def test_call_refusal_without_message_stays_plain_unavailable(monkeypatch, status):
    _install_response(monkeypatch, FakeResponse(status, None, text="oops"))
    with pytest.raises(AdapterUnavailableError) as excinfo:
        _do_call()
    assert not isinstance(excinfo.value, AdapterRejectedError)


def test_call_404_with_message_is_not_rejected(monkeypatch):
    _install_response(monkeypatch, FakeResponse(404, {"message": "Not found"}))
    with pytest.raises(AdapterUnavailableError) as excinfo:
        _do_call()
    assert not isinstance(excinfo.value, AdapterRejectedError)
    assert " returned 404" in str(excinfo.value)


def test_call_401_about_verification_token_is_rejected_not_auth(monkeypatch):
    _install_response(monkeypatch, FakeResponse(401, {"message": "Invalid or expired Verification token"}))
    with pytest.raises(AdapterRejectedError) as excinfo:
        _do_call()
    assert excinfo.value.bank_message == "Invalid or expired Verification token"


@pytest.mark.parametrize("status,body", [
    (401, {"message": "JWT expired"}),
    (401, None),
    (403, {"message": "Forbidden"}),
    (403, {"message": "verification required"}),
])
def test_call_plain_401_403_is_auth_error(monkeypatch, status, body):
    _install_response(monkeypatch, FakeResponse(status, body))
    with pytest.raises(AdapterAuthError):
        _do_call()


def test_call_success_returns_json(monkeypatch):
    _install_response(monkeypatch, FakeResponse(200, {"ok": True}))
    assert _do_call() == {"ok": True}
