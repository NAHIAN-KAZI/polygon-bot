"""A recharge or transfer for a named person looks the saved beneficiary up first (T-147)."""
import asyncio
import json

import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterResult
from app.banking.routing import BankingService, Clarification

RECHARGE = BankingService("app_actions", "mobile_recharge", None, {"amount": "100"})
SEND = BankingService("transfer", "wallet_transfer", "bkash", {"amount": "500"})
SAVED = {"beneficiaries": [{"nickname": "Jahid", "serviceType": "OTHER_BANK"}, {"nickname": "Rahima Begum", "serviceType": "MFS"}]}


def _run(result, message, choice, monkeypatch, identity=object(), token="jwt", saved=SAVED):
    seen = {}

    async def post(path, body, timeout=None):
        seen["prompt"] = body["prompt"]
        return {"response": json.dumps({"choice": choice})}

    async def fulfill(identity, jwt, category, service, subservice, payload):
        if saved is None:
            raise RuntimeError("bank down")
        return AdapterResult(data=saved)

    monkeypatch.setattr(chat_module.llm_backend, "post", post)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fulfill)
    got = asyncio.run(chat_module._named_person_lookup.real(result, message, identity, token))
    return got, seen


def test_a_saved_name_in_a_recharge_becomes_the_beneficiary_lookup_with_the_exact_saved_name(monkeypatch):
    got, seen = _run(RECHARGE, "jahid k 100 taka recharge koro", 1, monkeypatch)
    assert (got.category, got.service) == ("polygon_services", "beneficiary")
    assert got.payload == {"nameQuery": "Jahid", "purpose": "recharge", "amount": "100"}
    assert "1. Jahid" in seen["prompt"] and "2. Rahima Begum" in seen["prompt"]


def test_a_transfer_to_a_saved_name_is_a_lookup_too_without_a_recharge_purpose(monkeypatch):
    got, _ = _run(SEND, "rahima ke 500 taka pathao", 2, monkeypatch)
    assert got.payload == {"nameQuery": "Rahima Begum", "amount": "500"}


def test_a_message_that_names_nobody_saved_or_gives_a_number_is_left_alone(monkeypatch):
    assert _run(RECHARGE, "recharge koro", 0, monkeypatch)[0] is RECHARGE
    assert _run(RECHARGE, "recharge koro", 9, monkeypatch)[0] is RECHARGE                    # not a listed number
    assert _run(RECHARGE, "01712345678 e 50 taka recharge", 1, monkeypatch)[0] is RECHARGE   # a number, no model call
    own = BankingService("app_actions", "mobile_recharge", None, {"forSelf": "true"})
    assert _run(own, "amar number e recharge", 1, monkeypatch)[0] is own


def test_nothing_saved_a_bank_error_or_no_login_leaves_the_request_alone(monkeypatch):
    assert _run(RECHARGE, "jahid k recharge koro", 1, monkeypatch, saved={"beneficiaries": []})[0] is RECHARGE
    assert _run(RECHARGE, "jahid k recharge koro", 1, monkeypatch, saved=None)[0] is RECHARGE
    assert _run(RECHARGE, "jahid k recharge koro", 1, monkeypatch, identity=None)[0] is RECHARGE
    assert _run(RECHARGE, "jahid k recharge koro", 1, monkeypatch, token=None)[0] is RECHARGE


def test_other_results_are_left_alone(monkeypatch):
    unsure = Clarification(question="?", options=())
    assert _run(unsure, "help", 0, monkeypatch)[0] is unsure                   # names nobody saved
    other = BankingService("app_actions", "card_apply", None, {})
    assert _run(other, "jahid k recharge koro", 1, monkeypatch)[0] is other


def test_a_clarification_that_names_a_saved_person_becomes_a_lookup_to_send_money(monkeypatch):
    unsure = Clarification(question="where?", options=())
    got, _ = _run(unsure, "jahid ke 500 taka pathao", 1, monkeypatch)
    assert (got.category, got.service) == ("polygon_services", "beneficiary") and got.payload == {"nameQuery": "Jahid"}


def test_a_saved_mobile_recharge_beneficiary_opens_the_recharge_screen():
    assert chat_module._resolve_beneficiary_destination({"serviceType": "MOBILE_RECHARGE"}) == {"action": "mobile_recharge"}
    assert chat_module._resolve_beneficiary_destination({"serviceType": "CARD_PAYMENT"}) is None


# ---- a number the customer did not say never reaches a request (T-151) -----------------------------------------------------

def test_a_number_the_classifier_made_up_is_dropped_so_the_customer_is_asked():
    sent = BankingService("transfer", "wallet_transfer", "bkash", {"walletNumber": "01711111111", "amount": "500"})
    got = chat_module._check_numbers(sent, "শন এক আারি")
    assert got.payload == {"amount": "500"}


def test_a_number_that_is_in_the_message_stays_whatever_the_spacing_or_digits():
    for message in ("send to 01862610315", "send to 0186 261 0315", "send to 018-6261-0315", "নম্বর ০১৮৬২৬১০৩১৫"):
        sent = BankingService("transfer", "wallet_transfer", "bkash", {"walletNumber": "01862610315"})
        assert chat_module._check_numbers(sent, message) is sent


def test_other_results_and_payloads_without_numbers_are_untouched():
    plain = BankingService("account_info", "balance", None, {"nickname": "x"})
    assert chat_module._check_numbers(plain, "anything") is plain
    assert chat_module._check_numbers(Clarification(question="?", options=()), "x") is not None


# ---- a number the customer spoke is read back in full (T-152) -------------------------------------------------------------

def test_a_spoken_number_is_read_back_as_digit_groups_and_a_typed_one_is_not():
    token = chat_module._spoken_turn.set(True)
    try:
        got = chat_module._read_back("01862610315")
        assert got["number_as_heard"] == "0186 261 0315" and "read it back in full" in got["check_it"]
        assert chat_module._read_back("0186") == {} and chat_module._read_back(None) == {}
    finally:
        chat_module._spoken_turn.reset(token)
    assert chat_module._read_back("01862610315") == {}
