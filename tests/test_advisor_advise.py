import asyncio
import json
from datetime import date

import pytest

from app.advisor import advise, snapshot
from app.knowledge.product_cards import ProductCard

TODAY = date(2026, 10, 27)


def card(name, kind, **kw):
    return ProductCard(name=name, group=kw.pop("group", "Cards"), kind=kind, **kw)


CARDS = [
    card("Gold Credit", "credit card", summary="A rewards card.", best_for=["shopping"], min_monthly_income=60000,
         fees=["Annual fee BDT 3,000"], minimum=None),
    card("Everyday Debit", "debit card", summary="Daily banking."),
    card("Smart Saver", "savings account", group="Deposit accounts", min_opening_amount=1000,
         rates=["Up to 6%"], best_for=["building savings"]),
    card("Term Deposit", "fixed deposit", group="Deposit accounts", min_opening_amount=50000, min_age=18, max_age=70),
]
KINDS = advise.kinds_of(CARDS)


def summary(month, income, expense, cats):
    return {"month": month, "totalIncome": income, "totalExpense": expense,
            "expenseByCategory": [{"categoryName": n, "amount": a} for n, a in cats.items()]}


def snap(history=True):
    s = snapshot.Snapshot(as_of=TODAY)
    s.accounts = [{"accountNumber": "1234567890", "accountType": "SAVINGS"}]
    s.ledgers = [{"identifier": "1234567890", "balance": 6_900_000}]
    if history:
        s.history = [summary("2026-08", 9_000_000, 6_100_000, {"Food": 2_000_000, "Rent": 2_500_000, "Fun": 300_000}),
                     summary("2026-09", 9_000_000, 7_500_000, {"Food": 3_500_000, "Rent": 2_500_000, "Fun": 900_000})]
    return s


class Model:
    """A scripted model: answers by which question the prompt asks."""

    def __init__(self, monkeypatch, need=None, picks=None, coaching=None, fail=False):
        self.prompts = []
        answers = {"which kind": need, "which product": picks, "guidance on their spending": coaching}

        async def post(path, body, timeout=None):
            prompt = body["prompt"]
            self.prompts.append(prompt)
            if fail:
                raise RuntimeError("model down")
            for marker, answer in (("Decide what kind", need), ("which product suits them", picks),
                                   ("wants guidance on their spending", coaching)):
                if marker in prompt:
                    return {"response": json.dumps(answer if answer is not None else {})}
            raise AssertionError("unexpected prompt")

        monkeypatch.setattr(advise.llm_backend, "post", post)


# ---- need ----------------------------------------------------------------------------------------------------------

def test_the_need_prompt_lists_the_kinds_and_treats_the_message_as_data():
    prompt = advise.read_need_prompt("which card is best?", ["earlier"], KINDS)
    assert "1. credit card" in prompt and "fixed deposit" in prompt and "ignore them" in prompt and "earlier" in prompt


def test_a_valid_need_maps_kind_numbers_to_kinds():
    need = advise.parse_need({"spending": False, "product": True, "focus": "a card", "goal": "travel", "kinds": [1, 2]}, KINDS)
    assert need.product and not need.spending and need.kinds == (KINDS[0], KINDS[1]) and need.goal == "travel"


def test_unusable_needs_default_to_spending_guidance_and_a_product_need_without_kinds_is_not_one():
    for raw in (None, {}, {"spending": "yes"}, {"spending": False, "product": False}):
        assert advise.parse_need(raw, KINDS) == advise.Need(spending=True, product=False)
    need = advise.parse_need({"product": True, "kinds": [0, 99, True]}, KINDS)
    assert need.product is False and need.spending is True        # nothing to choose from: guide on spending instead


def test_both_can_be_wanted():
    need = advise.parse_need({"spending": True, "product": True, "kinds": [3]}, KINDS)
    assert need.spending and need.product and need.kinds == (KINDS[2],)


# ---- products ------------------------------------------------------------------------------------------------------

def test_candidates_are_the_cards_of_the_chosen_kinds():
    need = advise.Need(False, True, kinds=("savings account", "fixed deposit"))
    assert [c.name for c in advise.candidates(CARDS, need)] == ["Smart Saver", "Term Deposit"]


def test_picks_are_checked_numbers_only_no_repeats_at_most_three():
    cands = CARDS[:4]
    raw = {"picks": [{"number": 2, "reasons": ["saves 28%", "", 7], "keep_in_mind": "annual fee"},
                     {"number": 2, "reasons": ["again"]}, {"number": 9}, {"number": True}, "junk",
                     {"number": 1, "reasons": ["a"]}, {"number": 3}, {"number": 4}]}
    picks = advise.parse_picks(raw, cands)
    assert [p.card.name for p in picks] == ["Everyday Debit", "Gold Credit", "Smart Saver"]
    assert picks[0].reasons == ("saves 28%", "7") and picks[0].keep_in_mind == "annual fee"
    assert advise.parse_picks(None, cands) == [] and advise.parse_picks({"picks": "x"}, cands) == []


def test_requirements_are_compared_in_code_with_the_customers_figures():
    notes = advise.requirement_checks(CARDS[0], income_per_month=4_500_000, balance=None)
    assert notes == ["asks for a monthly income of Tk 60,000; theirs averages Tk 45,000 (is below it)"]
    notes = advise.requirement_checks(CARDS[0], income_per_month=9_000_000, balance=None)
    assert notes[0].endswith("(meets it)")
    notes = advise.requirement_checks(CARDS[3], income_per_month=None, balance=6_900_000)
    assert notes[0] == "asks for Tk 50,000 to open; their balance is Tk 69,000 (enough today)"
    assert "age range 18 to 70" in notes[1]
    assert advise.requirement_checks(CARDS[1], 1, 1) == []
    assert advise.requirement_checks(CARDS[0], None, None) == []     # unknown figures are not guessed


# ---- coaching ------------------------------------------------------------------------------------------------------

CATS = [{"name": "Rent", "per_month": 2_500_000, "share": 40.0, "last_complete_month": 2_500_000, "change_percent": 0.0},
        {"name": "Food", "per_month": 2_750_000, "share": 44.0, "last_complete_month": 3_500_000, "change_percent": 75.0},
        {"name": "Fun", "per_month": 600_000, "share": 9.6, "last_complete_month": 900_000, "change_percent": 200.0}]


def test_coaching_keeps_only_real_categories_and_sensible_percentages():
    raw = {"biggest": [2, 1, 9], "grew": [3], "cuts": [
        {"number": 3, "percent": 30, "how": "fewer outings"}, {"number": 3, "percent": 20},
        {"number": 2, "percent": 4}, {"number": 2, "percent": 80}, {"number": 1, "percent": "15"},
        {"number": 2, "percent": 12.4, "how": "cook at home"}, {"number": 7, "percent": 10}]}
    plan = advise.parse_coaching(raw, CATS)
    assert [c["name"] for c in plan["biggest"]] == ["Food", "Rent"] and [c["name"] for c in plan["grew"]] == ["Fun"]
    assert [(c["name"], p, how) for c, p, how in plan["cuts"]] == [("Fun", 30, "fewer outings"), ("Food", 12, "cook at home")]
    assert advise.parse_coaching(None, CATS) == {"biggest": [], "grew": [], "cuts": []}


def test_the_saving_is_computed_in_code_from_the_customers_own_category_totals():
    plan = {"biggest": [CATS[1]], "grew": [CATS[2]], "cuts": [(CATS[2], 30, "fewer outings"), (CATS[1], 10, "cook")]}
    facts = advise.coaching_facts(plan, CATS, {"coverage": {"complete_months": 2, "monthly_totals_from": "2026-08"}})
    assert facts["ways_to_save"][0] == {"category": "Fun", "cut_by_percent": 30, "how": "fewer outings",
                                        "would_save_per_month": "Tk 1,800"}
    assert facts["ways_to_save"][1]["would_save_per_month"] == "Tk 2,750"
    assert facts["total_possible_saving_per_month"] == "Tk 4,550"
    assert facts["history_covered"] == "2 complete month(s) of history, from 2026-08"


def test_with_no_cuts_there_is_no_total():
    facts = advise.coaching_facts({"biggest": [], "grew": [], "cuts": []}, CATS, {})
    assert "total_possible_saving_per_month" not in facts and [r["name"] for r in facts["where_the_money_goes"]] == ["Rent", "Food", "Fun"]
    assert facts["history_covered"] == "very little history to go on yet"


# ---- the whole thing -----------------------------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


def test_spending_guidance_end_to_end(monkeypatch):
    # complete months Aug and Sep: Food 5.5M, Rent 5.0M, Fun 1.2M poisha, so the model's numbers 1, 2, 3 are those
    model = Model(monkeypatch, coaching={"biggest": [1], "grew": [3], "cuts": [{"number": 3, "percent": 20, "how": "fewer outings"}]})
    result = run(advise.advise("where does my money go?", [], snap(), advise.Need(True, False, focus="spending"), CARDS))
    assert result.products == [] and result.used == "insights" and result.must == {}
    assert result.facts["where the money goes"][0]["name"] == "Food"
    assert result.facts["ways to save"] == [{"category": "Fun", "cut by percent": 20, "how": "fewer outings",
                                             "would save per month": "Tk 1,200"}]     # 20% of Tk 6,000 a month
    assert result.facts["total possible saving per month"] == "Tk 1,200"
    assert [c["name"] for c in result.insight["categories"]] == ["Food", "Rent", "Fun"] and len(model.prompts) == 1


def test_a_recommendation_end_to_end_with_lead_tags_must_names_and_code_side_checks(monkeypatch):
    Model(monkeypatch, picks={"picks": [{"number": 1, "reasons": ["saves Tk 18,875 a month"], "keep_in_mind": "annual fee"}]})
    need = advise.Need(False, True, focus="a deposit", goal="save", kinds=("savings account", "fixed deposit"))
    result = run(advise.advise("which deposit?", [], snap(), need, CARDS))
    product = result.facts["suggested products"][0]
    assert product["name"] == "Smart Saver" and product["why it fits"] == ["saves Tk 18,875 a month"]
    assert product["requirements against their figures"] == ["asks for Tk 1,000 to open; their balance is Tk 69,000 (enough today)"]
    assert product["rates"] == ["Up to 6%"] and product["keep in mind"] == "annual fee"
    assert result.must == {"suggested product 1": "Smart Saver"}
    assert result.products == [{"name": "Smart Saver", "group": "Deposit accounts", "strength": "info"}]
    assert result.used == "recommend" and result.facts["no product fits"] is None
    # income and spending carry unmistakable labels so a reply cannot swap them
    assert result.facts["their situation"] == {"average income per month": "Tk 90,000",
                                               "average spending per month": "Tk 68,000",
                                               "share of income left unspent (percent)": 24.4,
                                               "balance now": "Tk 69,000"}


def test_when_nothing_fits_that_is_said_and_no_lead_is_made(monkeypatch):
    Model(monkeypatch, picks={"picks": []})
    need = advise.Need(False, True, kinds=("credit card",))
    result = run(advise.advise("which card?", [], snap(), need, CARDS))
    assert result.facts["suggested products"] == [] and result.facts["no product fits"] and result.products == [] and result.must == {}


def test_both_wanted_gives_both_parts(monkeypatch):
    Model(monkeypatch, coaching={"cuts": [{"number": 1, "percent": 10, "how": "x"}]}, picks={"picks": [{"number": 1}]})
    need = advise.Need(True, True, kinds=("debit card",))
    facts = run(advise.advise("help me", [], snap(), need, CARDS)).facts
    assert "ways to save" in facts and facts["suggested products"][0]["name"] == "Everyday Debit"


def test_with_no_money_data_and_no_product_asked_there_is_nothing_to_go_on(monkeypatch):
    Model(monkeypatch)
    result = run(advise.advise("where does my money go?", [], snap(history=False), advise.Need(True, False), CARDS))
    assert "nothing to go on" in result.facts and result.products == []


def test_a_down_model_never_invents_anything(monkeypatch):
    Model(monkeypatch, fail=True)
    result = run(advise.advise("which card?", [], snap(), advise.Need(True, True, kinds=("credit card",)), CARDS))
    assert result.facts["ways to save"] == [] and result.facts["suggested products"] == [] and result.products == []
    assert run(advise.read_need("hi", [], CARDS)) == advise.Need(True, False)


def test_read_need_asks_the_model_with_the_card_kinds(monkeypatch):
    model = Model(monkeypatch, need={"spending": False, "product": True, "focus": "a deposit", "kinds": [3, 4]})
    need = run(advise.read_need("which deposit?", ["earlier"], CARDS))
    assert need.product and need.kinds == ("fixed deposit", "savings account")   # numbers 3 and 4 of the sorted kinds
    assert "credit card" in model.prompts[0] and "debit card" in model.prompts[0]


def test_each_pick_states_how_it_relates_to_what_the_customer_already_holds():
    raw = {"picks": [{"number": 1, "relation": "upgrade"}, {"number": 2, "relation": "extra"},
                     {"number": 3, "relation": "sideways"}]}
    picks = advise.parse_picks(raw, CARDS)
    assert [p.relation for p in picks] == ["upgrade", "extra", ""]       # an unknown word is no relation at all


def test_the_relation_reaches_the_reply_facts_as_a_plain_sentence(monkeypatch):
    Model(monkeypatch, picks={"picks": [{"number": 1, "reasons": ["x"], "relation": "extra"}]})
    need = advise.Need(False, True, kinds=("savings account",))
    facts = run(advise.advise("which?", [], snap(), need, CARDS)).facts
    assert facts["suggested products"][0]["compared with what they hold"] == \
        "they already hold one of this kind and this would be another"


def test_when_applying_the_facts_are_a_short_list_and_a_question_without_the_financial_summary(monkeypatch):
    Model(monkeypatch, picks={"picks": [{"number": 1, "reasons": ["one", "two", "three"], "keep_in_mind": "fee",
                                          "relation": "new"}]})
    need = advise.Need(False, True, kinds=("savings account",))
    facts = run(advise.advise("which?", [], snap(), need, CARDS, applying=True)).facts
    product = facts["suggested products"][0]
    assert "their situation" not in facts and product["why it fits"] == ["one", "two"]
    assert product["fees"] == [] and product["rates"] == [] and product["keep in mind"] is None
    assert facts["next step"].startswith("ask which of these")
    # without applying the full picture is given
    full = run(advise.advise("which?", [], snap(), need, CARDS)).facts
    assert "their situation" in full and "next step" not in full


def test_a_need_that_names_products_offers_only_those_whatever_their_kind():
    need = advise.Need(False, True, names=("Gold Credit", "Smart Saver"))
    assert [c.name for c in advise.candidates(CARDS, need)] == ["Gold Credit", "Smart Saver"]
    # kinds are ignored when names are given; with no names the kinds decide, as before
    assert [c.name for c in advise.candidates(CARDS, advise.Need(False, True, kinds=("debit card",)))] == ["Everyday Debit"]
