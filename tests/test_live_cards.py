"""The bank's live card list reaches the answer (T-145)."""
import asyncio

import pytest

from app.knowledge import live_cards
from app.llm import build_prompt

BODY = {"status": "success", "data": [
    {"active": True, "cardCategory": "DEBIT", "scheme": "VISA", "tierName": "Polygon Visa Debit Card",
     "description": "Everyday debit.", "domesticNetworks": ["NPSB"], "internationalNetworks": ["VISA"]},
    {"active": True, "cardCategory": "CREDIT", "scheme": "MASTERCARD", "tierName": "Polygon Mastercard World Elite Credit Card",
     "description": "Premium credit.", "domesticNetworks": ["NPSB"], "internationalNetworks": ["MASTERCARD"]},
    {"active": True, "cardCategory": "CREDIT", "scheme": "VISA", "tierName": "Polygon Visa Platinum Card",
     "description": "", "domesticNetworks": [], "internationalNetworks": ["VISA"]},
    {"active": False, "cardCategory": "DEBIT", "scheme": "VISA", "tierName": "Retired Card"},
    {"active": True, "cardCategory": "DEBIT", "scheme": "VISA", "tierName": "Polygon Visa Debit Card"},
]}


@pytest.fixture(autouse=True)
def _fresh():
    live_cards.clear_cache()
    yield
    live_cards.clear_cache()


def test_parse_keeps_every_active_card_once_in_order():
    cards = live_cards.parse(BODY)
    assert [c["name"] for c in cards] == ["Polygon Visa Debit Card", "Polygon Mastercard World Elite Credit Card",
                                          "Polygon Visa Platinum Card"]
    assert cards[1]["type"] == "credit" and cards[1]["network"] == "Mastercard"


def test_parse_accepts_a_bare_list_a_wrapped_list_and_junk():
    assert len(live_cards.parse(BODY["data"])) == 3
    assert len(live_cards.parse({"cardProducts": BODY["data"]})) == 3
    assert live_cards.parse(None) == [] and live_cards.parse({"data": "x"}) == []


def test_prompt_block_splits_debit_and_credit_and_names_each_card():
    block = live_cards.prompt_block(live_cards.parse(BODY))
    assert "Debit cards (1):" in block and "Credit cards (2):" in block
    assert "- Polygon Visa Platinum Card (Visa)" in block
    assert "- Polygon Mastercard World Elite Credit Card (Mastercard): Premium credit." in block


def test_build_prompt_puts_the_list_before_the_passages_and_still_works_without_passages():
    block = live_cards.prompt_block(live_cards.parse(BODY))
    with_hits = build_prompt("which cards", [{"filename": "kb.md", "text": "Gold gives lounge access."}], None, block)
    assert with_hits.index("Polygon Visa Platinum Card") < with_hits.index("Gold gives lounge access.")
    assert "name every card in it" in with_hits
    alone = build_prompt("which cards", [], None, block)
    assert "Polygon Visa Platinum Card" in alone and "no information on this question" not in alone
    assert "name every card" not in build_prompt("which cards", [{"filename": "k", "text": "t"}], None, None)


def test_current_fetches_with_the_login_then_serves_the_kept_list_signed_out(monkeypatch):
    calls = []

    class Fake:
        async def fulfill(self, identity, jwt, sub, payload):
            calls.append(jwt)
            from app.banking.adapters.base import AdapterResult
            return AdapterResult(data=BODY)

    monkeypatch.setattr(live_cards, "CardProductsAdapter", Fake)
    run = asyncio.run
    assert run(live_cards.current(None)) == []                     # nothing kept yet, no login
    first = run(live_cards.current("jwt-1"))
    assert len(first) == 3
    assert run(live_cards.current("jwt-2")) == first and calls == ["jwt-1"]   # kept
    assert run(live_cards.current(None)) == first                  # signed out gets the kept list


def test_current_falls_back_to_nothing_when_the_bank_fails(monkeypatch):
    class Boom:
        async def fulfill(self, *a):
            raise RuntimeError("down")

    monkeypatch.setattr(live_cards, "CardProductsAdapter", Boom)
    assert asyncio.run(live_cards.current("jwt")) == []
