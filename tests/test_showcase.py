"""Products as the app draws them: a card as its artwork, any other product as a tile, ranked when recommended (T-171)."""
import pytest

from app.advisor import advise as advise_module
from app.knowledge import showcase
from app.knowledge.product_cards import ProductCard

import app.routes.chat as chat_module
from tests.test_advice_flow import CARDS, advice, ask  # noqa: F401 -- the fixture and the helper of the advice flow

LIVE = [{"name": "Polygon Gold Debit", "type": "debit", "network": "Visa", "scheme_code": "VISA",
         "routing_profile": None, "capabilities": ["CONTACTLESS"], "description": "", "networks": []},
        {"name": "Polygon World Elite", "type": "credit", "network": "Mastercard", "scheme_code": "MASTERCARD",
         "routing_profile": None, "capabilities": [], "description": "", "networks": []}]
GOLD = ProductCard("Polygon Gold Debit", "Cards", "debit card", summary="A gold debit card.", fees=["Annual fee BDT 500"])
ELITE = ProductCard("Polygon World Elite", "Cards", "credit card", benefits=["Lounge access"])
LOAN = ProductCard("Personal Loan", "Loans and finance", "personal loan", summary="A loan.", minimum="BDT 50,000",
                   rates=["Please click here to find the interest rate" * 3, "11.5% a year"],
                   fees=["the bank's schedule of charges applies", "Processing fee 1%"])
FDR = ProductCard("Fixed Deposit Account", "Deposit accounts", "fixed deposit account", minimum="BDT 50,000")


def test_a_card_the_live_list_has_is_drawn_as_artwork_and_any_other_product_as_a_tile():
    card = showcase.item(GOLD, LIVE)
    assert card["visual"] == "card" and card["cardType"] == "debit" and card["scheme"] == "VISA"
    assert card["capabilities"] == ["CONTACTLESS"] and card["details"]["fees"] == ["Annual fee BDT 500"]
    tile = showcase.item(LOAN, LIVE)
    assert tile["visual"] == "tile" and tile["family"] == "loan" and "scheme" not in tile
    assert tile["facts"] == [{"label": "Minimum", "value": "BDT 50,000"}, {"label": "Rate", "value": "11.5% a year"},
                             {"label": "Fee", "value": "Processing fee 1%"}]          # long text and the generic charges line are left out
    assert showcase.item(FDR, LIVE)["family"] == "deposit"


def test_a_card_that_is_not_in_the_live_list_is_a_tile_not_a_made_up_picture():
    assert showcase.item(ProductCard("Polygon Old Card", "Cards", "credit card"), LIVE)["visual"] == "tile"


def test_picks_stay_in_one_ranked_row_with_their_reasons():
    built = showcase.build([showcase.item(ELITE, LIVE, rank=1, why=["spends 15,000 a month", ""], keep_in_mind="check the limit"),
                            showcase.item(GOLD, LIVE, rank=2)], ranked=True)
    assert built["ranked"] and len(built["sections"]) == 1
    first, second = built["sections"][0]["items"]
    assert (first["rank"], first["why"], first["keepInMind"]) == (1, ["spends 15,000 a month"], "check the limit")
    assert second["rank"] == 2 and second["why"] == []


def test_a_list_gets_a_row_per_card_kind_then_a_row_per_group_of_products():
    built = showcase.build([showcase.item(LOAN, LIVE), showcase.item(ELITE, LIVE), showcase.item(GOLD, LIVE),
                            showcase.item(FDR, LIVE)])
    assert [(s["title"], s["family"]) for s in built["sections"]] == [
        ("Debit cards", "debit"), ("Credit cards", "credit"), ("Deposit accounts", "deposit"), ("Loans and finance", "loan")]
    assert showcase.build([]) is None


# ---- in the chat ---------------------------------------------------------------------------------------------------------

def test_a_recommendation_carries_the_picked_products_ranked_with_the_reasons_given(client, advice):
    advice["advice"] = advise_module.Advice(
        {"suggested products": [{"name": "Smart Saver"}]}, must={"suggested product 1": "Smart Saver"},
        products=[{"name": "Smart Saver", "group": "Deposit accounts", "strength": "info"}], choices=["Smart Saver"],
        ranking=[{"name": "Smart Saver", "fit": "best", "why": ["it pays on their balance"], "keep_in_mind": "min balance"}],
        used="recommend")
    _, result, _ = ask(client)
    built = result["payload"]["showcase"]
    item = built["sections"][0]["items"][0]
    assert built["ranked"] and item["name"] == "Smart Saver" and item["rank"] == 1
    assert item["why"] == ["it pays on their balance"] and item["keepInMind"] == "min balance"


def test_a_card_question_without_debit_or_credit_asks_which_and_shows_both_rows(client, advice, monkeypatch):
    cards = [ProductCard("Gold Debit", "Cards", "debit card", apply_via="card_apply"),
             ProductCard("Gold Credit", "Cards", "credit card", apply_via="credit_card_apply")]
    monkeypatch.setattr(chat_module.product_cards, "all_cards", lambda: cards)
    live = [{**LIVE[0], "name": "Gold Debit"}, {**LIVE[1], "name": "Gold Credit"}]

    async def current(*a, **k):
        return live

    monkeypatch.setattr(chat_module.live_cards_mod, "current", current)
    advice["need"] = advise_module.Need(spending=False, product=True, focus="best card", kinds=("credit card", "debit card"))
    reply, result, _ = ask(client, message="which card is best for me?")
    assert result["type"] == "CLARIFICATION_REQUIRED" and advice["calls"] == ["read_need"]      # nothing was ranked yet
    sections = result["payload"]["showcase"]["sections"]
    assert [s["family"] for s in sections] == ["debit", "credit"] and sections[0]["items"][0]["visual"] == "card"
    assert "debit cards" in reply and "credit cards" in reply


def test_the_reply_that_picks_a_kind_is_then_ranked_among_that_kind_only(client, advice, monkeypatch):
    cards = [ProductCard("Gold Debit", "Cards", "debit card", apply_via="card_apply"),
             ProductCard("Gold Credit", "Cards", "credit card", apply_via="credit_card_apply")]
    monkeypatch.setattr(chat_module.product_cards, "all_cards", lambda: cards)
    advice["need"] = advise_module.Need(spending=False, product=True, focus="best card", kinds=("credit card", "debit card"))
    ask(client, message="which card is best for me?")

    async def pick(message, names, offered=True):
        return names.index("credit cards")

    monkeypatch.setattr(chat_module, "_llm_pick_name", pick)
    _, result, _ = ask(client, message="the credit one")
    assert result["type"] == "ADVICE_ANSWER"
    assert advice["need_used"].kinds == ("credit card",) and advice["need_used"].product


def test_a_card_question_that_already_says_which_kind_is_not_asked_again(client, advice, monkeypatch):
    cards = [ProductCard("Gold Debit", "Cards", "debit card"), ProductCard("Gold Credit", "Cards", "credit card")]
    monkeypatch.setattr(chat_module.product_cards, "all_cards", lambda: cards)
    advice["need"] = advise_module.Need(spending=False, product=True, focus="best credit card", kinds=("credit card",))
    _, result, _ = ask(client, message="which credit card is best for me?")
    assert result["type"] == "ADVICE_ANSWER"
