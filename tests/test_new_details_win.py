"""What the customer says now beats what an older, unfinished request left behind (T-155)."""
import asyncio

import app.routes.chat as chat_module
from app.banking.routing import BankingService


def _run(merged, fresh, message, monkeypatch, amount=None, wallet=None, must_not_ask=False):
    async def fill(key, subservice, payload, fields, question, message):
        assert not must_not_ask, "the amount was read again although this message gave one"
        return BankingService(key[0], key[1], subservice, {"amount": amount}) if amount is not None else None

    async def read(message):
        return wallet

    monkeypatch.setattr(chat_module, "_fill_fields", fill)
    monkeypatch.setattr(chat_module, "_read_wallet_provider", read)
    return asyncio.run(chat_module._prefer_new_details(merged, fresh, message))


def _pair(old_payload, new_payload, old_sub="upay", new_sub=None):
    fresh = BankingService("transfer", "wallet_transfer", new_sub, new_payload)
    merged = BankingService("transfer", "wallet_transfer", new_sub or old_sub, {**old_payload, **new_payload})
    return merged, fresh


def test_a_whole_new_request_replaces_the_amount_and_wallet_an_unfinished_one_left(monkeypatch):
    merged, fresh = _pair({"amount": 50}, {"walletNumber": "01862610315"})
    got = _run(merged, fresh, "Please send 300 taka on nagad to 01862610315.", monkeypatch, amount=300, wallet="nagad")
    assert got.payload == {"amount": 300, "walletNumber": "01862610315"} and got.subservice == "nagad"


def test_a_reply_that_only_answers_the_question_keeps_everything_carried(monkeypatch):
    merged, fresh = _pair({"amount": 50}, {"walletNumber": "01862610315"})
    assert _run(merged, fresh, "01862610315", monkeypatch) is merged


def test_a_detail_the_classifier_read_from_this_message_is_not_looked_at_again(monkeypatch):
    merged, fresh = _pair({"amount": 50}, {"amount": 300, "walletNumber": "01862610315"})
    assert _run(merged, fresh, "send 300 to 01862610315", monkeypatch, must_not_ask=True) is merged


def test_the_same_amount_stays_and_a_wallet_the_classifier_named_is_kept(monkeypatch):
    merged, fresh = _pair({"amount": 50}, {"walletNumber": "01862610315"})
    assert _run(merged, fresh, "50 taka, number 01862610315", monkeypatch, amount=50) is merged
    merged, fresh = _pair({"amount": 50}, {"walletNumber": "01862610315"}, new_sub="nagad")
    assert _run(merged, fresh, "nagad 01862610315", monkeypatch, wallet="upay").subservice == "nagad"   # the classifier's own reading stands


def test_a_number_of_their_own_replaces_an_old_one_the_classifier_did_not_replace(monkeypatch):
    merged, fresh = _pair({"amount": 50, "walletNumber": "01711223344"}, {})
    got = _run(merged, fresh, "make it 01862610315 instead", monkeypatch)
    assert "walletNumber" not in (got.payload or {}) and got.payload["amount"] == 50


def test_other_services_and_results_are_left_alone(monkeypatch):
    other = BankingService("account_info", "balance", None, {"x": 1})
    assert _run(other, BankingService("transfer", "bank_transfer", None, {}), "hi", monkeypatch) is other
    assert _run(other, other, "hi", monkeypatch) is other
