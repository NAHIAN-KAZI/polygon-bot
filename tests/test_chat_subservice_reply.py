"""Direct unit tests for _subservice_reply() in app/routes/chat.py (TASKS.md T-27).

T-27 rewrote _subservice_reply(service, subservice, data) -> str to build
real, data-driven spoken reply text per subservice (balance/accounts/
device_history/transaction_history/login_history) instead of a single
generic templated line, with defensive type-checking and a
try/except Exception: return fallback around every branch so malformed
adapter data can never crash the /chat stream.

These call _subservice_reply directly (imported from app.routes.chat, same
underscore-prefixed-helper-import pattern the rest of this test suite already
follows for other module-private helpers, e.g. record_turn/get_classification_
context fakes installed via monkeypatch.setattr(chat_module, ...) throughout
test_chat_banking_flow.py) rather than going through the full SSE stream --
existing tests (test_chat_banking_flow.py, test_chat_integration_contract.py)
already cover the end-to-end wiring; this file is purely about locking in the
reply-text contract and the "never raises" safety property for every branch,
using the exact live-confirmed payload shapes recorded in TASKS.md T-27.
"""
from app.routes.chat import _subservice_reply


# --- 1. balance: unchanged behavior ------------------------------------------


def test_balance_unchanged_behavior():
    data = {"balance": 100226007015}
    assert _subservice_reply("balance", None, data) == "Your available balance is 100226007015."


# --- 2. accounts --------------------------------------------------------------


def test_accounts_single_account_singular_sentence():
    data = {
        "data": {
            "accounts": [
                {
                    "accountName": "Test Savings",
                    "accountNumber": "100126000015",
                    "accountType": "SAVINGS",
                    "balance": "0.00",
                }
            ],
            "ledgerAccounts": [{"accountNumber": "999999999999", "accountType": "LEDGER"}],
        },
        "status": "success",
    }
    reply = _subservice_reply("accounts", None, data)
    assert reply == "You have 1 account: Savings (ending 0015)."
    # ledgerAccounts must never leak into the summary.
    assert "999999999999" not in reply
    assert "Ledger" not in reply


def test_accounts_multiple_mixed_types_plural_sentence():
    data = {
        "data": {
            "accounts": [
                {"accountName": "A", "accountNumber": "100126000015", "accountType": "SAVINGS"},
                {"accountName": "B", "accountNumber": "100126000099", "accountType": "SAVINGS"},
                {"accountName": "C", "accountNumber": None, "accountType": "FIXED_DEPOSIT"},
            ]
        }
    }
    reply = _subservice_reply("accounts", None, data)
    assert reply == (
        "You have 3 accounts: Savings (ending 0015), Savings (ending 0099), Fixed Deposit."
    )


def test_accounts_empty_list_no_accounts_sentence():
    data = {"data": {"accounts": []}}
    assert _subservice_reply("accounts", None, data) == "You don't have any accounts on record."


def test_accounts_malformed_missing_data_key_falls_back():
    data = {"status": "success"}
    assert _subservice_reply("accounts", None, data) == "Sure — here's information about accounts."


def test_accounts_malformed_accounts_not_a_list_falls_back():
    data = {"data": {"accounts": "oops"}}
    assert _subservice_reply("accounts", None, data) == "Sure — here's information about accounts."


def test_accounts_malformed_data_itself_not_a_dict_falls_back():
    assert _subservice_reply("accounts", None, "not a dict") == (
        "Sure — here's information about accounts."
    )


# --- 3. device_history ---------------------------------------------------------


def test_device_history_single_device():
    data = {"devices": [{"deviceName": "Xiaomi 2201116PI", "platform": "ANDROID"}]}
    assert _subservice_reply("device_history", None, data) == (
        "You have 1 device linked: Xiaomi 2201116PI."
    )


def test_device_history_multiple_devices():
    data = {
        "devices": [
            {"deviceName": "Xiaomi 2201116PI", "platform": "ANDROID"},
            {"deviceName": "iPhone 14", "platform": "IOS"},
        ]
    }
    assert _subservice_reply("device_history", None, data) == (
        "You have 2 devices linked: Xiaomi 2201116PI, iPhone 14."
    )


def test_device_history_empty_list_no_devices_sentence():
    data = {"devices": []}
    assert _subservice_reply("device_history", None, data) == "You don't have any devices on record."


def test_device_history_malformed_devices_not_a_list_falls_back():
    data = {"devices": "oops"}
    assert _subservice_reply("device_history", None, data) == (
        "Sure — here's information about device history."
    )


def test_device_history_malformed_missing_devices_key_falls_back():
    data = {}
    assert _subservice_reply("device_history", None, data) == (
        "Sure — here's information about device history."
    )


# --- 4. transaction_history -----------------------------------------------------


def test_transaction_history_normal_case_mentions_counts_and_latest():
    data = {
        "transactions": [
            {
                "description": "Mobile Recharge: From 100126000015 to 4900000",
                "amount": 2000,
                "type": "DEBIT",
                "txnTime": "2026-09-06T17:45:38.596336+06:00",
            },
            {
                "description": "Some other transaction",
                "amount": 500,
                "type": "CREDIT",
                "txnTime": "2026-09-05T10:00:00+06:00",
            },
        ],
        "pagination": {"totalCount": 12, "currentPageTotalCount": 10, "hasNext": True},
        "openingBalance": 0,
    }
    reply = _subservice_reply("transaction_history", None, data)
    assert "2 most recent transactions" in reply
    assert "out of 12 total" in reply
    assert "৳2000" in reply
    assert "Mobile Recharge: From 100126000015 to 4900000" in reply
    assert "debit" in reply


def test_transaction_history_total_count_equals_shown_no_out_of_total():
    data = {
        "transactions": [
            {"description": "Txn A", "amount": 10, "type": "DEBIT"},
            {"description": "Txn B", "amount": 20, "type": "CREDIT"},
            {"description": "Txn C", "amount": 30, "type": "DEBIT"},
        ],
        "pagination": {"totalCount": 3, "currentPageTotalCount": 3, "hasNext": False},
    }
    reply = _subservice_reply("transaction_history", None, data)
    assert "3 most recent transactions" in reply
    assert "out of" not in reply


def test_transaction_history_empty_list_no_transactions_sentence():
    data = {"transactions": [], "pagination": {"totalCount": 0}}
    assert _subservice_reply("transaction_history", None, data) == (
        "You don't have any recent transactions."
    )


def test_transaction_history_malformed_falls_back():
    assert _subservice_reply("transaction_history", None, {"transactions": "oops"}) == (
        "Sure — here's information about transaction history."
    )
    assert _subservice_reply("transaction_history", None, {}) == (
        "Sure — here's information about transaction history."
    )


# --- 5. login_history ------------------------------------------------------------


def test_login_history_real_records_key_mentions_count_and_latest():
    data = {
        "records": [
            {
                "status": "SUCCESS",
                "loginType": "BIOMETRIC",
                "ipAddress": "10.42.6.247",
                "deviceName": "Xiaomi 2201116PI",
                "loginAt": "2026-09-06T17:45:38.596336+06:00",
            },
            {
                "status": "SUCCESS",
                "loginType": "PASSWORD",
                "ipAddress": "10.42.6.200",
                "deviceName": "Xiaomi 2201116PI",
                "loginAt": "2026-09-05T09:00:00+06:00",
            },
        ],
        "pagination": {"totalCount": 21, "currentPage": 0, "currentPageTotalCount": 5, "hasNext": True},
    }
    reply = _subservice_reply("login_history", None, data)
    assert "2 most recent logins" in reply
    assert "out of 21 total" in reply
    assert "success" in reply
    assert "10.42.6.247" in reply


def test_login_history_empty_records_no_history_sentence():
    data = {"records": [], "pagination": {"totalCount": 0}}
    assert _subservice_reply("login_history", None, data) == (
        "There's no login history on record for this device."
    )


def test_login_history_malformed_missing_records_key_falls_back():
    data = {"pagination": {"totalCount": 0}}
    assert _subservice_reply("login_history", None, data) == (
        "Sure — here's information about login history."
    )


def test_login_history_malformed_records_not_a_list_falls_back():
    data = {"records": "oops"}
    assert _subservice_reply("login_history", None, data) == (
        "Sure — here's information about login history."
    )


# --- 6. unknown service/subservice falls back to the generic sentence ----------


def test_unknown_service_subservice_falls_back_to_generic_sentence():
    assert _subservice_reply("some_unknown_service", "some_unknown_subservice", {"foo": "bar"}) == (
        "Sure — here's information about some unknown service."
    )


# --- 7. no branch ever raises for malformed/edge inputs -------------------------


def test_no_exception_for_any_malformed_input_across_all_known_services():
    malformed_payloads = [
        None,
        [],
        123,
        "a string",
        {},
        {"data": None},
        {"data": {"accounts": None}},
        {"data": {"accounts": [1, 2, 3]}},
        {"devices": None},
        {"devices": [None, 1, "x"]},
        {"transactions": None},
        {"transactions": [{"amount": None, "description": None, "type": None}]},
        {"pagination": "not a dict", "transactions": [{"amount": 1, "description": "x", "type": "DEBIT"}]},
        {"records": None},
        {"records": [{"status": None, "ipAddress": None}]},
        {"records": [1, 2, 3]},
    ]
    services = ["balance", "accounts", "device_history", "transaction_history", "login_history", "made_up_service"]

    for service in services:
        for payload in malformed_payloads:
            # Must never raise -- this is the core safety property T-27
            # guarantees. A plain call (no try/except here) is enough: if
            # anything raised, pytest would report this test as an error.
            reply = _subservice_reply(service, None, payload)
            assert isinstance(reply, str)
            assert reply != ""
