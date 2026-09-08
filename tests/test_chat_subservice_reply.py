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

TASKS.md T-29 added _synthesize_reply(message, service, subservice, data) ->
str: an LLM-synthesized spoken reply (via Ollama /api/generate, using
settings.OLLAMA_MODEL -- the RAG/generation model, deliberately NOT
settings.OLLAMA_CLASSIFY_MODEL) that falls back to the existing deterministic
_subservice_reply() template on any failure -- network error, non-200 status,
malformed JSON body, or an empty/whitespace-only response string -- so a
flaky/slow Ollama can never crash or block the /chat stream. The Ollama HTTP
layer is mocked by monkeypatching httpx.AsyncClient.post directly, matching
this codebase's existing style (see tests/test_routing.py's FakeResponse
pattern) rather than pulling in a new test dependency like respx.
_synthesize_reply is async and driven via asyncio.run(), matching
tests/test_adapter_base.py (no pytest-asyncio in this repo).
"""
import asyncio
import json

import httpx

from app.config import settings
from app.routes.chat import _account_card_summary, _subservice_reply, _synthesize_reply


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


# --- 2b. accounts + card mention integration (T-28) ----------------------------


def test_accounts_with_number_and_one_active_card_includes_both_in_parenthetical():
    data = {
        "data": {
            "accounts": [
                {
                    "accountName": "Test Savings",
                    "accountNumber": "100126000015",
                    "accountType": "SAVINGS",
                    "cards": [{"cardType": "DEBIT", "status": "ACTIVE"}],
                }
            ]
        }
    }
    reply = _subservice_reply("accounts", None, data)
    assert reply == "You have 1 account: Savings (ending 0015, linked to 1 debit card)."


def test_accounts_with_number_but_no_cards_has_only_ending_no_card_mention():
    data = {
        "data": {
            "accounts": [
                {
                    "accountName": "Test Savings",
                    "accountNumber": "100126000015",
                    "accountType": "SAVINGS",
                    "cards": [],
                }
            ]
        }
    }
    reply = _subservice_reply("accounts", None, data)
    assert reply == "You have 1 account: Savings (ending 0015)."
    assert "linked to" not in reply
    assert ", )" not in reply


def test_accounts_with_no_number_and_no_cards_falls_back_to_bare_type_no_parens():
    data = {
        "data": {
            "accounts": [
                {
                    "accountName": "Test Fixed",
                    "accountNumber": None,
                    "accountType": "FIXED_DEPOSIT",
                    "cards": [],
                }
            ]
        }
    }
    reply = _subservice_reply("accounts", None, data)
    assert reply == "You have 1 account: Fixed Deposit."
    assert "(" not in reply
    assert ")" not in reply


def test_accounts_multiple_only_some_with_cards_each_parenthetical_independent():
    data = {
        "data": {
            "accounts": [
                {
                    "accountName": "A",
                    "accountNumber": "100126000015",
                    "accountType": "SAVINGS",
                    "cards": [{"cardType": "DEBIT", "status": "ACTIVE"}],
                },
                {
                    "accountName": "B",
                    "accountNumber": "100126000099",
                    "accountType": "SAVINGS",
                    "cards": [],
                },
                {
                    "accountName": "C",
                    "accountNumber": None,
                    "accountType": "FIXED_DEPOSIT",
                },
            ]
        }
    }
    reply = _subservice_reply("accounts", None, data)
    assert reply == (
        "You have 3 accounts: Savings (ending 0015, linked to 1 debit card), "
        "Savings (ending 0099), Fixed Deposit."
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


# --- 8. _account_card_summary direct unit tests (T-28) --------------------------


def test_card_summary_none_returns_empty_string():
    assert _account_card_summary(None) == ""


def test_card_summary_empty_list_returns_empty_string():
    assert _account_card_summary([]) == ""


def test_card_summary_not_a_list_returns_empty_string():
    assert _account_card_summary({"cardType": "DEBIT"}) == ""
    assert _account_card_summary("oops") == ""


def test_card_summary_single_active_debit_card_singular():
    cards = [{"cardType": "DEBIT", "status": "ACTIVE"}]
    assert _account_card_summary(cards) == "linked to 1 debit card"


def test_card_summary_two_active_debit_cards_plural():
    cards = [
        {"cardType": "DEBIT", "status": "ACTIVE"},
        {"cardType": "DEBIT", "status": "ACTIVE"},
    ]
    assert _account_card_summary(cards) == "linked to 2 debit cards"


def test_card_summary_three_distinct_types_breakdown_in_list_order():
    cards = [
        {"cardType": "DEBIT", "status": "ACTIVE"},
        {"cardType": "CREDIT", "status": "ACTIVE"},
        {"cardType": "PREPAID", "status": "ACTIVE"},
    ]
    # Implementation counts into a dict keyed by lowercased cardType and
    # iterates it in insertion order, so the breakdown follows the order
    # types first appear in the input list.
    assert _account_card_summary(cards) == "linked to 3 cards (1 debit, 1 credit, 1 prepaid)"


def test_card_summary_blocked_card_excluded_from_count():
    cards = [
        {"cardType": "DEBIT", "status": "ACTIVE"},
        {"cardType": "DEBIT", "status": "BLOCKED"},
    ]
    assert _account_card_summary(cards) == "linked to 1 debit card"


def test_card_summary_missing_status_treated_as_active():
    cards = [{"cardType": "DEBIT"}]
    assert _account_card_summary(cards) == "linked to 1 debit card"


def test_card_summary_missing_card_type_skipped_not_counted():
    cards = [{"status": "ACTIVE"}]
    assert _account_card_summary(cards) == ""


def test_card_summary_non_dict_entry_skipped_valid_entry_still_counted():
    cards = ["not a card", {"cardType": "DEBIT", "status": "ACTIVE"}]
    assert _account_card_summary(cards) == "linked to 1 debit card"


# --- 9. _synthesize_reply direct unit tests (T-29) ------------------------------


class _FakeResponse:
    """Mirrors tests/test_routing.py's FakeResponse: a minimal stand-in for
    httpx.Response supporting raise_for_status()/json(), with json() able to
    raise (simulating a malformed/non-JSON response body)."""

    def __init__(self, json_data=None, status_code=200, json_exc=None):
        self._json_data = json_data
        self.status_code = status_code
        self._json_exc = json_exc

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_data


def _install_post_response(monkeypatch, json_data=None, status_code=200, json_exc=None, captured_calls=None):
    async def fake_post(self, url, *args, **kwargs):
        if captured_calls is not None:
            captured_calls.append({"url": url, "kwargs": kwargs})
        return _FakeResponse(json_data=json_data, status_code=status_code, json_exc=json_exc)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _install_post_raises(monkeypatch, exc):
    async def fake_post(self, url, *args, **kwargs):
        raise exc

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def test_synthesize_reply_success_returns_ollama_text_exactly(monkeypatch):
    _install_post_response(monkeypatch, json_data={"response": "Your balance is real and specific."})
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, {"balance": 100}))
    assert result == "Your balance is real and specific."


def test_synthesize_reply_success_strips_whitespace(monkeypatch):
    _install_post_response(monkeypatch, json_data={"response": "  some text  \n"})
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, {"balance": 100}))
    assert result == "some text"


def test_synthesize_reply_non_200_status_falls_back_to_subservice_reply(monkeypatch):
    _install_post_response(monkeypatch, json_data={"response": "irrelevant, should never be seen"}, status_code=500)
    data = {"balance": 100}
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, data))
    assert result == _subservice_reply("balance", None, data)
    assert result == "Your available balance is 100."


def test_synthesize_reply_connect_error_falls_back_no_exception_propagates(monkeypatch):
    _install_post_raises(monkeypatch, httpx.ConnectError("connection refused"))
    data = {"balance": 100}
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, data))
    assert result == _subservice_reply("balance", None, data)


def test_synthesize_reply_timeout_falls_back_no_exception_propagates(monkeypatch):
    _install_post_raises(monkeypatch, httpx.TimeoutException("request timed out"))
    data = {"balance": 100}
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, data))
    assert result == _subservice_reply("balance", None, data)


def test_synthesize_reply_empty_string_response_falls_back(monkeypatch):
    _install_post_response(monkeypatch, json_data={"response": ""})
    data = {"balance": 100}
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, data))
    assert result == _subservice_reply("balance", None, data)


def test_synthesize_reply_whitespace_only_response_falls_back(monkeypatch):
    """Confirms the implementation strips first, then checks falsy -- not
    just an exact-empty-string check -- per TASKS.md T-29."""
    _install_post_response(monkeypatch, json_data={"response": "   "})
    data = {"balance": 100}
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, data))
    assert result == _subservice_reply("balance", None, data)


def test_synthesize_reply_malformed_json_body_falls_back_no_exception_propagates(monkeypatch):
    _install_post_response(monkeypatch, json_exc=ValueError("not valid json"))
    data = {"balance": 100}
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, data))
    assert result == _subservice_reply("balance", None, data)


def test_synthesize_reply_missing_response_key_falls_back(monkeypatch):
    """Belt-and-suspenders for the `result.get("response") or ""` guard --
    a response body with no "response" key at all must also fall back
    rather than raising a KeyError."""
    _install_post_response(monkeypatch, json_data={"unexpected": "shape"})
    data = {"balance": 100}
    result = asyncio.run(_synthesize_reply("what's my balance", "balance", None, data))
    assert result == _subservice_reply("balance", None, data)


def test_synthesize_reply_sends_correct_request_body(monkeypatch):
    """Locks in the outbound Ollama request contract: uses
    settings.OLLAMA_MODEL (the RAG/generation model) -- NOT
    settings.OLLAMA_CLASSIFY_MODEL -- with stream=False and think matching
    settings.OLLAMA_THINK, and a prompt that contains both the original
    message and the fetched data's content."""
    captured_calls = []
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "test-rag-model")
    monkeypatch.setattr(settings, "OLLAMA_CLASSIFY_MODEL", "test-classify-model-must-not-be-used")
    monkeypatch.setattr(settings, "OLLAMA_THINK", True)
    _install_post_response(monkeypatch, json_data={"response": "ok"}, captured_calls=captured_calls)

    data = {"balance": "distinctive-marker-999888777"}
    asyncio.run(_synthesize_reply("what is my balance please", "balance", None, data))

    assert len(captured_calls) == 1
    body = captured_calls[0]["kwargs"]["json"]
    assert body["model"] == "test-rag-model"
    assert body["model"] != "test-classify-model-must-not-be-used"
    assert body["stream"] is False
    assert body["think"] is True
    assert "what is my balance please" in body["prompt"]
    assert "distinctive-marker-999888777" in body["prompt"]


# --- 10. _synthesize_reply prompt redaction (T-35) --------------------------


def test_synthesize_reply_prompt_redacts_raw_account_number_uses_masked_sibling(monkeypatch):
    """_synthesize_reply must run `data` through _redact_for_prompt before
    embedding it in the Ollama prompt, so a raw account number (with an
    accountNumberMasked sibling already present, as T-32's _enrich_payload
    adds before this is called) never reaches the model."""
    captured_calls = []
    _install_post_response(monkeypatch, json_data={"response": "ok"}, captured_calls=captured_calls)

    data = {
        "balance": "500.00",
        "accountNumber": "1234567890",
        "accountNumberMasked": "••••••7890",
    }
    asyncio.run(_synthesize_reply("what's my balance", "balance", "balance", data))

    assert len(captured_calls) == 1
    prompt = captured_calls[0]["kwargs"]["json"]["prompt"]
    assert "1234567890" not in prompt
    # json.dumps(..., default=str) escapes the non-ASCII "•" bullet, so look
    # for its JSON-encoded form rather than the literal character.
    assert json.dumps("••••••7890")[1:-1] in prompt


def test_synthesize_reply_prompt_redacts_cif_and_nid(monkeypatch):
    captured_calls = []
    _install_post_response(monkeypatch, json_data={"response": "ok"}, captured_calls=captured_calls)

    data = {"balance": "500.00", "cifNumber": "CIF-000111", "nid": "1234567890123"}
    asyncio.run(_synthesize_reply("what's my balance", "balance", "balance", data))

    prompt = captured_calls[0]["kwargs"]["json"]["prompt"]
    assert "CIF-000111" not in prompt
    assert "1234567890123" not in prompt
    assert "[redacted]" in prompt
