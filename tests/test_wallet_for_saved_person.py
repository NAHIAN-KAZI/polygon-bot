"""A wallet the customer names opens that wallet's transfer for a saved person, and the person can be saved under it (T-153)."""
import asyncio
import json
from datetime import datetime, timezone

import app.routes.chat as chat_module
from app.banking.session import ChatTurn
from tests.test_chat_beneficiary_matching import (
    ASHAN, ASHANUR, JWT_HEADERS, _install_beneficiary_fixture, _parse_sse)

WALLETS = ["bkash", "nagad", "rocket", "upay"]
DIPU = {"id": 38, "nickname": "dipu", "accountHolderName": "Dipu", "serviceType": "MOBILE_RECHARGE",
        "mfsProvider": None, "accountNumber": "01711229005"}


def _wallets(monkeypatch):
    monkeypatch.setattr(chat_module, "_wallet_ids", lambda: WALLETS)


def _ask(client, message="dipu k bkash e 500 taka pathabo"):
    events = _parse_sse(client.post("/chat", json={"message": message}, headers=JWT_HEADERS).text)
    return (next(d for n, d in events if n == "result"), "".join(d.get("token", "") for n, d in events if n == "token"))


def test_a_person_saved_for_recharge_opens_the_wallet_transfer_the_customer_named(client, monkeypatch):
    _wallets(monkeypatch)
    _install_beneficiary_fixture(monkeypatch, [DIPU, ASHAN], payload={"nameQuery": "dipu", "amount": "500", "provider": "bkash"})
    result, text = _ask(client)
    assert result["type"] == "BENEFICIARY_MATCH"
    assert result["payload"]["destination"] == {"action": "wallet_transfer", "provider": "bkash"}
    assert result["payload"]["provider"] == "bkash" and result["payload"]["amount"] == "500"
    assert result["routing"]["action"] == "wallet_transfer"
    assert "the wallet they want: bkash" in text and "saving them as a bkash beneficiary too" in text


def test_the_wallet_is_read_from_the_words_when_the_classifier_did_not_carry_it(client, monkeypatch):
    _wallets(monkeypatch)
    _install_beneficiary_fixture(monkeypatch, [DIPU], payload={"nameQuery": "dipu", "amount": "500"})

    async def read(message):
        return "nagad"

    monkeypatch.setattr(chat_module, "_read_wallet_provider", read)
    result, _ = _ask(client)
    assert result["payload"]["destination"] == {"action": "wallet_transfer", "provider": "nagad"} and result["payload"]["provider"] == "nagad"


def test_no_wallet_named_keeps_the_kind_the_person_is_saved_as_and_offers_nothing(client, monkeypatch):
    _wallets(monkeypatch)
    _install_beneficiary_fixture(monkeypatch, [DIPU], payload={"nameQuery": "dipu", "amount": "500"})

    async def read(message):
        return None

    monkeypatch.setattr(chat_module, "_read_wallet_provider", read)
    result, text = _ask(client)
    assert result["payload"]["destination"] == {"action": "mobile_recharge"} and "provider" not in result["payload"]
    assert "saving them as" not in text


def test_a_person_saved_as_a_bank_account_is_not_sent_to_a_wallet(client, monkeypatch):
    _wallets(monkeypatch)
    _install_beneficiary_fixture(monkeypatch, [ASHAN], payload={"nameQuery": "Ashan", "provider": "bkash"})
    result, _ = _ask(client, "ashan k bkash e pathabo")
    assert result["payload"]["destination"] == {"action": "own_bank_transfer"}     # no mobile number to use


def test_the_wallet_and_amount_travel_with_the_choice_when_several_people_match(client, monkeypatch):
    _wallets(monkeypatch)
    _install_beneficiary_fixture(monkeypatch, [ASHAN, ASHANUR], payload={"nameQuery": "Ashan", "amount": "500", "provider": "nagad"})
    result, _ = _ask(client)
    assert result["type"] == "BENEFICIARY_SELECTION_REQUIRED"
    assert result["payload"]["provider"] == "nagad" and result["payload"]["amount"] == "500"


def test_only_a_wallet_the_bank_lists_is_carried(monkeypatch):
    _wallets(monkeypatch)
    assert chat_module._provider_prefill({"provider": "Bkash"}) == {"provider": "bkash"}
    assert chat_module._provider_prefill({"provider": "paypal"}) == {} and chat_module._provider_prefill({}) == {}


def test_the_wallet_reader_answers_from_the_banks_list_with_a_quote_that_is_in_the_message(monkeypatch):
    _wallets(monkeypatch)
    answers = {}

    async def post(path, body, timeout=None):
        return {"response": json.dumps(answers)}

    monkeypatch.setattr(chat_module.llm_backend, "post", post)

    def read(message, **a):
        answers.clear()
        answers.update(a)
        return asyncio.run(chat_module._read_wallet_provider(message))

    assert read("dipu k bkash e 500 taka pathabo", provider="bkash", quote="bkash") == "bkash"
    assert read("dipu k nogod e pathabo", provider="Nagad", quote="nogod") == "nagad"            # any spelling, listed name back
    assert read("dipu k taka pathabo", provider="bkash", quote="bkash") is None                    # words the customer never wrote
    assert read("dipu k paypal e pathabo", provider="paypal", quote="paypal") is None              # not a listed wallet
    assert read("dipu k taka pathabo", provider=None) is None


def _turn(classification):
    return [ChatTurn(timestamp=datetime.now(timezone.utc), message="x", classification=classification)]


OFFER = {"type": "BENEFICIARY_MATCH", "pending_save": {"leafServiceId": "bkash", "nickname": "dipu", "accountNumber": "01711229005"}}


def test_agreeing_to_the_offer_gives_the_form_values_and_anything_else_does_not(monkeypatch):
    answers = {}

    async def post(path, body, timeout=None):
        return {"response": json.dumps(answers)}

    monkeypatch.setattr(chat_module.llm_backend, "post", post)

    def reply(agree):
        answers.clear()
        answers["agree"] = agree
        return asyncio.run(chat_module._try_save_offer(_turn(OFFER), "ha koro"))

    assert reply(True) == {"leafServiceId": "bkash", "nickname": "dipu", "accountNumber": "01711229005"}
    assert reply(False) is None and reply("yes") is None
    assert asyncio.run(chat_module._try_save_offer(_turn({"type": "KB_ANSWER"}), "ha")) is None
    assert asyncio.run(chat_module._try_save_offer(_turn({"type": "BENEFICIARY_MATCH"}), "ha")) is None
    assert asyncio.run(chat_module._try_save_offer([], "ha")) is None
