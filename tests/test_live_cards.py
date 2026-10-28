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


# ---- merge: the cards a customer can actually ask for ---------------------------------------------------------------

from app.knowledge.product_cards import ProductCard  # noqa: E402

LIVE = live_cards.parse({"data": [
    {"active": True, "cardCategory": "DEBIT", "scheme": "VISA", "tierName": "Polygon Visa Debit Card", "description": "Debit."},
    {"active": True, "cardCategory": "DEBIT", "scheme": "VISA", "tierName": "Polygon Digital Visa Platinum Debit Card",
     "description": "Digital debit."},
    {"active": True, "cardCategory": "DEBIT", "scheme": "TAKAPAY", "tierName": "Polygon TakaPay Debit Card",
     "description": "Domestic. Launch later: needs membership."},
    {"active": True, "cardCategory": "CREDIT", "scheme": "VISA", "tierName": "Polygon Visa Platinum Card", "description": "Credit."},
    {"active": True, "cardCategory": "CREDIT", "scheme": "VISA", "tierName": "Polygon Visa Infinite Credit Card", "description": "Premium."},
    {"active": True, "cardCategory": "CREDIT", "scheme": "VISA", "tierName": "Polygon Islamic Visa Infinite Credit Card",
     "description": "Shariah."},
]})
STORED = [
    ProductCard("Visa Platinum", "Cards", "credit card", "KB platinum.", benefits=["lounge"], best_for=["travel"], apply_via="credit_card_apply"),
    ProductCard("Visa Infinite", "Cards", "credit card", "KB infinite.", fees=["Tk 5,000 a year"], apply_via="credit_card_apply"),
    ProductCard("Polygon Visa SME Credit Card", "Cards", "credit card", "Business.", apply_via="credit_card_apply"),
    ProductCard("Polygon Visa Debit Card", "Cards", "debit card", "KB debit.", apply_via="card_apply"),
    ProductCard("Gold DPS", "Deposit accounts", "dps", "Saves monthly.", apply_via="dps_open"),
]


def _by_name(cards):
    return {c.name: c for c in cards}


def test_merge_names_every_live_card_as_the_bank_does_and_enriches_it_from_the_knowledge_base():
    merged = _by_name(live_cards.merge(STORED, LIVE))
    platinum = merged["Polygon Visa Platinum Card"]
    assert platinum.benefits == ["lounge"] and "Credit." in platinum.summary and "KB platinum." in platinum.summary
    assert platinum.kind == "credit card" and platinum.apply_via == "credit_card_apply"
    assert merged["Polygon Visa Infinite Credit Card"].fees == ["Tk 5,000 a year"]      # the plain one, not the Islamic one
    assert merged["Polygon Islamic Visa Infinite Credit Card"].fees == []               # live card with no knowledge-base twin
    assert merged["Polygon Visa Debit Card"].apply_via == "card_apply"
    assert merged["Polygon TakaPay Debit Card"].summary.endswith("Launch later: needs membership.")


def test_merge_drops_a_card_product_the_app_cannot_request_and_keeps_other_products():
    merged = _by_name(live_cards.merge(STORED, LIVE))
    assert "Polygon Visa SME Credit Card" not in merged and "Visa Platinum" not in merged
    assert merged["Gold DPS"].apply_via == "dps_open"
    assert len([c for c in merged.values() if c.apply_via in ("card_apply", "credit_card_apply")]) == len(LIVE)


def test_merge_without_a_live_list_changes_nothing():
    assert live_cards.merge(STORED, []) == STORED
