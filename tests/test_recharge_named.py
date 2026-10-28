"""A recharge for a named person looks the saved beneficiary up first (T-147)."""
import asyncio
import json

import app.routes.chat as chat_module
from app.banking.routing import BankingService, Clarification

RECHARGE = BankingService("app_actions", "mobile_recharge", None, {"amount": "100"})


def _run(result, message, answer, identity=object(), monkeypatch=None):
    async def post(path, body, timeout=None):
        return {"response": json.dumps(answer)}

    monkeypatch.setattr(chat_module.llm_backend, "post", post)
    return asyncio.run(chat_module._recharge_for_named_person(result, message, identity))


def test_a_name_without_a_number_becomes_the_saved_beneficiary_lookup(monkeypatch):
    got = _run(RECHARGE, "jahid k 100 taka recharge koro", {"person": "jahid", "quote": "jahid"}, monkeypatch=monkeypatch)
    assert (got.category, got.service) == ("polygon_services", "beneficiary")
    assert got.payload == {"nameQuery": "jahid", "purpose": "recharge", "amount": "100"}


def test_a_number_their_own_number_or_a_made_up_name_leaves_the_recharge_alone(monkeypatch):
    named = {"person": "jahid", "quote": "jahid"}
    assert _run(RECHARGE, "01712345678 e 50 taka recharge koro", named, monkeypatch=monkeypatch) is RECHARGE
    own = BankingService("app_actions", "mobile_recharge", None, {"forSelf": "true"})
    assert _run(own, "amar number e recharge", named, monkeypatch=monkeypatch) is own
    assert _run(RECHARGE, "recharge koro", {"person": "Rahim", "quote": "Rahim"}, monkeypatch=monkeypatch) is RECHARGE
    assert _run(RECHARGE, "recharge koro", {"person": None}, monkeypatch=monkeypatch) is RECHARGE
    assert _run(RECHARGE, "jahid k recharge koro", named, identity=None, monkeypatch=monkeypatch) is RECHARGE


def test_other_results_are_left_alone(monkeypatch):
    unsure = Clarification(question="?", options=())
    assert _run(unsure, "jahid k recharge koro", {"person": "jahid", "quote": "jahid"}, monkeypatch=monkeypatch) is unsure
    other = BankingService("app_actions", "card_apply", None, {})
    assert _run(other, "jahid k recharge koro", {"person": "jahid", "quote": "jahid"}, monkeypatch=monkeypatch) is other


def test_a_saved_mobile_recharge_beneficiary_opens_the_recharge_screen():
    assert chat_module._resolve_beneficiary_destination({"serviceType": "MOBILE_RECHARGE"}) == {"action": "mobile_recharge"}
    assert chat_module._resolve_beneficiary_destination({"serviceType": "CARD_PAYMENT"}) is None
