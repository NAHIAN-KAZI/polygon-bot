"""Personal advice in the chat: login, switches, the reply and what is exposed (T-132, T-135)."""
import json
from datetime import date

import pytest

import app.routes.chat as chat_module
from app.advisor import advise as advise_module
from app.advisor import snapshot as snapshot_module
from app.banking.adapters.base import AdapterAuthError
from app.banking.identity import CustomerIdentity
from app.banking.routing import AdviceQuestion
from app.knowledge.product_cards import ProductCard

from tests.conftest import AUTH_HEADERS

JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
CARDS = [ProductCard("Smart Saver", "Deposit accounts", "savings account")]
NEED = advise_module.Need(spending=True, product=True, focus="where my money goes", kinds=("savings account",))


def parse(body):
    out = []
    for block in body.strip("\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            out.append((name, data))
    return out


@pytest.fixture
def advice(monkeypatch):
    """The chat classified as an advice question, a signed-in customer, and the advice pieces recorded."""
    state = {"calls": [], "need": NEED, "snapshot_error": None,
             "advice": advise_module.Advice(
                 {"what_they_asked_about": "where my money goes", "where_the_money_goes": [{"name": "Food"}]},
                 must={"suggested product 1": "Smart Saver"},
                 products=[{"name": "Smart Saver", "group": "Deposit accounts", "strength": "info"}],
                 insight={"monthly": [], "categories": [{"name": "Food"}]}, used="recommend")}

    async def classify(message, recent_turns=None, app_notes=None):
        return AdviceQuestion()

    async def verify_jwt(token):
        return CustomerIdentity(customer_id="cust-advice")

    async def read_need(message, recent, cards):
        state["calls"].append("read_need")
        return state["need"]

    async def get_snapshot(identity, jwt):
        state["calls"].append("snapshot")
        if state["snapshot_error"]:
            raise state["snapshot_error"]
        return snapshot_module.Snapshot(as_of=date(2026, 10, 27))

    async def advise(message, recent, snap, need, cards, applying=False, customer_key=None, previous=None):
        state["calls"].append("advise")
        state["need_used"] = need
        return state["advice"]

    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "verify_jwt", verify_jwt)
    monkeypatch.setattr(chat_module.audit, "log_banking_turn", lambda *a, **k: None)
    monkeypatch.setattr(chat_module.advisor_advise, "read_need", read_need)
    monkeypatch.setattr(chat_module.advisor_advise, "advise", advise)
    monkeypatch.setattr(chat_module.advisor_snapshot, "get", get_snapshot)
    monkeypatch.setattr(chat_module.product_cards, "all_cards", lambda: CARDS)
    return state


def ask(client, headers=JWT_HEADERS, **body):
    resp = client.post("/chat", json={"message": "which deposit suits me?", **body}, headers=headers)
    assert resp.status_code == 200
    events = parse(resp.text)
    reply = "".join(d.get("token", "") for n, d in events if n == "token")
    return reply, next((d for n, d in events if n == "result"), {}), [n for n, _ in events]


def test_signed_in_the_reply_is_composed_from_the_facts_and_carries_lead_tags(client, advice):
    reply, result, names = ask(client)
    assert advice["calls"] == ["read_need", "snapshot", "advise"]
    assert result["type"] == "ADVICE_ANSWER" and result["category"] == "advisor" and result["service"] == "recommend"
    assert result["payload"]["products"] == [{"name": "Smart Saver", "group": "Deposit accounts", "strength": "info"}]
    assert result["payload"]["insight"] == {"monthly": [], "categories": [{"name": "Food"}]}
    assert names[-1] == "done" and names.count("result") == 1
    # the composer was given the facts and had to name the product
    assert reply.startswith("advice:") and "Smart Saver" in reply and "where the money goes" in reply


def test_signed_out_it_asks_for_a_login_and_reads_nothing(client, advice):
    reply, result, _ = ask(client, headers=AUTH_HEADERS)
    assert result["type"] == "AUTH_REQUIRED" and advice["calls"] == []
    assert reply.startswith("login_needed:")


def test_a_login_lost_during_the_fetch_is_reported_as_one(client, advice):
    advice["snapshot_error"] = AdapterAuthError("expired")
    _, result, _ = ask(client)
    assert result["type"] == "AUTH_REQUIRED" and "advise" not in advice["calls"]


def test_the_bank_failing_gives_a_plain_unavailable_answer_not_an_error(client, advice):
    advice["snapshot_error"] = RuntimeError("bank down")
    reply, result, names = ask(client)
    assert result["type"] == "SERVICE_UNAVAILABLE" and reply.startswith("unavailable:") and "error" not in names


def test_both_switches_off_does_nothing_before_the_switch_check(client, advice):
    _, result, _ = ask(client, disabled_use_cases=["advisor.insights", "advisor.recommend"])
    assert result["type"] == "USE_CASE_DISABLED" and result["payload"]["useCaseDisabled"] is True
    assert advice["calls"] == []


def test_the_product_switch_off_removes_products_but_keeps_spending_guidance(client, advice):
    _, result, _ = ask(client, disabled_use_cases=["advisor.recommend"])
    need = advice["need_used"]
    assert need.spending and not need.product and need.kinds == () and advice["calls"][-1] == "advise"
    assert result["type"] == "ADVICE_ANSWER"


def test_the_spending_switch_off_removes_guidance_but_keeps_products(client, advice):
    ask(client, disabled_use_cases=["advisor.insights"])
    need = advice["need_used"]
    assert need.product and not need.spending


def test_asking_only_for_what_is_switched_off_says_it_is_off(client, advice):
    advice["need"] = advise_module.Need(spending=False, product=True, kinds=("savings account",))
    _, result, _ = ask(client, disabled_use_cases=["advisor.recommend"])
    assert result["type"] == "USE_CASE_DISABLED" and result["payload"]["useCase"] == "advisor.recommend"
    assert "snapshot" not in advice["calls"]
    advice["need"] = advise_module.Need(spending=True, product=False)
    _, result, _ = ask(client, disabled_use_cases=["advisor.insights"])
    assert result["payload"]["useCase"] == "advisor.insights" and "snapshot" not in advice["calls"]


def test_a_spending_only_answer_has_no_lead_tags(client, advice):
    advice["advice"] = advise_module.Advice({"where_the_money_goes": [{"name": "Food"}]}, used="insights")
    _, result, _ = ask(client)
    assert result["service"] == "insights" and "products" not in result["payload"]


def test_the_result_is_not_a_knowledge_answer_so_the_back_office_stores_a_placeholder(client, advice):
    _, result, _ = ask(client)
    assert result["type"] != "KB_ANSWER"   # ChatTurnPolicy keeps full text only for KB_ANSWER


# ---- apply: suggest first, then open the application (T-140) --------------------------------------------------------

from datetime import datetime, timezone

from app.banking import ui_actions
from app.banking.routing import BankingService
from app.banking.session import ChatTurn, record_turn
from app.banking import session as session_module


CARDS_FOR_APPLY = [ProductCard("Platinum Debit", "Cards", "debit card", apply_via="card_apply"),
                   ProductCard("Gold Debit", "Cards", "prepaid card", apply_via="card_apply"),
                   ProductCard("Gold Credit", "Cards", "credit card")]           # no screen opens a credit card


@pytest.fixture
def apply_flow(advice, monkeypatch):
    """A signed-in customer who says they want to apply for a card; the picker is scripted."""
    state = {"picked": None, "classify_calls": 0, "cards": CARDS_FOR_APPLY}
    advice["advice"] = advise_module.Advice(
        {"suggested products": [{"name": "Platinum Debit"}, {"name": "Gold Debit"}]},
        must={"suggested product 1": "Platinum Debit", "suggested product 2": "Gold Debit"},
        products=[{"name": "Platinum Debit", "group": "Cards", "strength": "info"},
                  {"name": "Gold Debit", "group": "Cards", "strength": "info"}],
        choices=["Platinum Debit", "Gold Debit"], used="recommend")

    async def classify(message, recent_turns=None, app_notes=None):
        state["classify_calls"] += 1
        return BankingService("app_actions", "card_apply", None, {})

    async def pick(message, names, offered=True):
        state.setdefault("asked", []).append(list(names))
        return state["picked"]

    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "_llm_pick_name", pick)
    monkeypatch.setattr(chat_module, "is_valid_path", lambda *a, **k: True)
    monkeypatch.setattr(chat_module.product_cards, "all_cards", lambda: state["cards"])
    return state


def say(client, message, **body):
    resp = client.post("/chat", json={"message": message, **body}, headers=JWT_HEADERS)
    events = parse(resp.text)
    return ("".join(d.get("token", "") for n, d in events if n == "token"),
            next((d for n, d in events if n == "result"), {}))


def test_wanting_to_apply_without_naming_a_product_suggests_first_and_does_not_open_the_form(client, apply_flow, advice):
    reply, result = say(client, "I want to apply for a debit card")
    assert result["type"] == "ADVICE_ANSWER" and "ui" not in (result.get("payload") or {})
    assert [p["name"] for p in result["payload"]["products"]] == ["Platinum Debit", "Gold Debit"]
    assert advice["calls"][-1] == "advise" and "read_need" not in advice["calls"]
    # the model was only ever shown the products whose card says this screen opens them
    assert apply_flow["asked"][0] == ["Platinum Debit", "Gold Debit"]
    assert advice["need_used"].names == ("Platinum Debit", "Gold Debit")


def test_a_first_message_that_picks_a_product_opens_the_form_with_it_chosen_and_suggests_nothing(client, apply_flow, advice):
    apply_flow["picked"] = 0
    reply, result = say(client, "I want to apply for the Platinum Debit card")
    assert result["type"] == "APP_ACTION" and result["payload"]["ui"]["route"] == "/request_virtual_card/form"
    assert result["payload"]["products"] == [{"name": "Platinum Debit", "group": "Cards", "strength": "apply"}]
    assert "snapshot" not in advice["calls"] and "Platinum Debit" in reply


def test_with_the_product_suggestions_switched_off_the_form_opens_at_once(client, apply_flow, advice):
    _, result = say(client, "I want to apply for a debit card", disabled_use_cases=["advisor.recommend"])
    assert result["type"] == "APP_ACTION" and "asked" not in apply_flow and advice["calls"] == []


def test_nothing_to_suggest_still_opens_the_form(client, apply_flow, advice):
    advice["advice"] = advise_module.Advice({"suggested products": []}, used="insights")
    _, result = say(client, "I want to apply for a debit card")
    assert result["type"] == "APP_ACTION" and result["payload"]["ui"]["route"] == "/request_virtual_card/form"


def test_the_bank_being_down_still_opens_the_form(client, apply_flow, advice):
    advice["snapshot_error"] = RuntimeError("bank down")
    _, result = say(client, "I want to apply for a debit card")
    assert result["type"] == "APP_ACTION"


def test_no_product_card_says_this_screen_opens_it_so_the_form_opens_at_once(client, apply_flow, advice):
    apply_flow["cards"] = [ProductCard("Gold Credit", "Cards", "credit card"), ProductCard("Old", "Cards", "debit card")]
    _, result = say(client, "I want to apply for a debit card")
    assert result["type"] == "APP_ACTION" and "asked" not in apply_flow and advice["calls"] == []


def test_choosing_one_of_the_suggestions_opens_the_form_and_the_chosen_product_is_the_lead(client, apply_flow, advice):
    say(client, "I want to apply for a debit card")                   # the suggestion turn is remembered
    apply_flow["picked"] = 1                                           # "the second one"
    classify_before = apply_flow["classify_calls"]
    reply, result = say(client, "the second one")
    assert apply_flow["asked"][-1] == ["Platinum Debit", "Gold Debit"]
    assert result["type"] == "APP_ACTION" and result["payload"]["ui"]["route"] == "/request_virtual_card/form"
    assert result["payload"]["products"] == [{"name": "Gold Debit", "group": "Cards", "strength": "apply"}]
    assert "Gold Debit" in reply and apply_flow["classify_calls"] == classify_before   # no new classification needed


def test_a_reply_that_picks_none_of_them_goes_through_normal_routing(client, apply_flow, advice):
    say(client, "I want to apply for a debit card")
    apply_flow["picked"] = None
    before = apply_flow["classify_calls"]
    say(client, "actually what is the fee for a transfer?")
    assert apply_flow["classify_calls"] == before + 1


def test_the_choice_is_ignored_when_the_apply_use_case_has_been_switched_off_meanwhile(client, apply_flow, advice):
    say(client, "I want to apply for a debit card")
    apply_flow["picked"] = 0
    _, result = say(client, "the first", disabled_use_cases=["app_actions.card_apply"])
    assert result["type"] in ("USE_CASE_DISABLED", "APP_ACTION") and result["payload"].get("useCaseDisabled") is True


def test_the_picker_accepts_only_a_valid_number_and_treats_the_reply_as_data(monkeypatch):
    import asyncio

    seen = {}

    async def post(path, body, timeout=None):
        seen["prompt"] = body["prompt"]
        return {"response": json.dumps({"choice": seen["answer"]})}

    monkeypatch.setattr(chat_module.llm_backend, "post", post)
    for answer, expected in ((2, 1), (0, None), (3, None), (True, None), ("1", None), (-1, None)):
        seen["answer"] = answer
        assert asyncio.run(chat_module._llm_pick_name("the gold one", ["Platinum Debit", "Gold Debit"])) == expected
    assert "ignore them" in seen["prompt"] and "1. Platinum Debit" in seen["prompt"]
    assert "only one product was offered" in seen["prompt"] and "offered these products" in seen["prompt"]
    asyncio.run(chat_module._llm_pick_name("I want the gold one", ["Platinum Debit", "Gold Debit"], offered=False))
    assert "might be asking about" in seen["prompt"] and "by naming it clearly" in seen["prompt"]
    assert "only one product was offered" not in seen["prompt"]       # a first message is not an answer to an offer


def test_a_first_message_picks_a_product_only_when_the_quoted_words_are_in_it(monkeypatch):
    import asyncio

    answers = {}

    async def post(path, body, timeout=None):
        return {"response": json.dumps(answers)}

    monkeypatch.setattr(chat_module.llm_backend, "post", post)
    names = ["Platinum Debit", "Gold Debit"]

    def pick(message, **answer):
        answers.clear()
        answers.update(answer)
        return asyncio.run(chat_module._llm_pick_name(message, names, offered=False))

    assert pick("I want the Gold Debit one", choice=2, quote="gold debit") == 1
    assert pick("I want a debit card", choice=2, quote="Gold Debit") is None       # words the customer never wrote
    assert pick("I want a debit card", choice=2) is None                          # no quote
    assert pick("I want a debit card", choice=2, quote="  ") is None
    assert pick("I want a debit card", choice=0, quote="debit card") is None


def test_a_message_the_classifier_could_not_place_becomes_the_application_it_says_it_wants(monkeypatch):
    import asyncio

    from app.banking.routing import Clarification

    answers = {}

    async def post(path, body, timeout=None):
        answers["prompt"] = body["prompt"]
        return {"response": json.dumps(answers.get("answer", {}))}

    monkeypatch.setattr(chat_module.llm_backend, "post", post)
    unsure = Clarification(question="what do you mean?", options=())
    identity = object()

    def look(message, answer, identity=identity, disabled=None, result=unsure):
        answers["answer"] = answer
        return asyncio.run(chat_module._second_look_apply.real(result, message, identity, disabled))

    got = look("debit card nite chai", {"action": 1, "quote": "nite chai"})
    assert got.category == "app_actions" and got.service == "card_apply"
    assert "Apply for a virtual card" in answers["prompt"] and "Apply for a credit card" in answers["prompt"]
    assert look("credit card nite chai", {"action": 2, "quote": "credit card nite chai"}).service == "credit_card_apply"
    assert look("debit card ki", {"action": 1, "quote": "nite chai"}) is unsure          # words not in the message
    assert look("debit card nite chai", {"action": 0, "quote": "nite chai"}) is unsure   # the model says no
    assert look("debit card nite chai", {"action": 9, "quote": "nite chai"}) is unsure   # not a listed number
    assert look("debit card nite chai", {"action": 1, "quote": "nite chai"}, identity=None) is unsure   # signed out
    off = look("debit card nite chai", {"action": 1, "quote": "nite chai"}, disabled=["app_actions.card_apply"])
    assert off.service != "card_apply"                                                      # a switched-off screen is not offered
    kept = BankingService("account_info", "balance", None, {})
    assert look("debit card nite chai", {"action": 1, "quote": "nite chai"}, result=kept) is kept   # only an unsure result is looked at again


def test_a_recommendation_remembers_which_screen_opens_what_it_suggested_so_choosing_one_opens_it(client, apply_flow, advice, monkeypatch):
    async def classify(message, recent_turns=None, app_notes=None):
        return AdviceQuestion()

    monkeypatch.setattr(chat_module, "classify", classify)
    _, result = say(client, "which debit card is best for me")
    assert result["type"] == "ADVICE_ANSWER"
    apply_flow["picked"] = 0
    _, result = say(client, "the first one")
    assert result["type"] == "APP_ACTION" and result["payload"]["ui"]["route"] == "/request_virtual_card/form"
    assert result["payload"]["products"] == [{"name": "Platinum Debit", "group": "Cards", "strength": "apply"}]


def test_a_recommendation_of_products_that_open_different_screens_remembers_each_products_screen(client, apply_flow, advice, monkeypatch):
    async def classify(message, recent_turns=None, app_notes=None):
        return AdviceQuestion()

    monkeypatch.setattr(chat_module, "classify", classify)
    apply_flow["cards"] = [ProductCard("Platinum Debit", "Cards", "debit card", apply_via="card_apply"),
                           ProductCard("Gold Debit", "Cards", "debit card", apply_via="credit_card_apply")]
    say(client, "which debit card is best for me")
    apply_flow["picked"] = 0
    asked = len(apply_flow.get("asked", []))
    _, result = say(client, "the first one")
    assert len(apply_flow.get("asked", [])) == asked + 1                                # a choice was looked for
    assert result["type"] == "APP_ACTION" and result["payload"]["ui"]["route"] == "/request_virtual_card/form"


def test_the_chosen_card_and_its_type_go_to_the_form_as_its_prefill(client, apply_flow, advice):
    say(client, "I want to apply for a debit card")
    apply_flow["picked"] = 1
    _, result = say(client, "the second one")
    assert result["payload"]["ui"]["prefill"] == {"cardProduct": "Gold Debit", "cardType": "prepaid"}


def test_a_first_message_naming_the_card_prefills_it_too(client, apply_flow, advice):
    apply_flow["picked"] = 0
    _, result = say(client, "I want to apply for the Platinum Debit card")
    assert result["payload"]["ui"]["prefill"] == {"cardProduct": "Platinum Debit", "cardType": "debit"}


def test_the_credit_card_form_has_no_product_to_prefill_and_the_reply_does_not_ask_to_pick_one(client, apply_flow, advice, monkeypatch):
    action = ui_actions.get("credit_card_apply")
    outcome = chat_module._ui_action_outcome(action, {"requestedLimit": "300000"}, "credit card, limit 300000 taka",
                                             None, {"name": "Gold Credit", "group": "Cards", "type": None})
    prefill = outcome.result_payload["ui"]["prefill"]
    assert prefill == {"requestedLimit": "300000"} and "cardProduct" not in prefill
    facts = outcome.say[1]
    assert "no choice of product" in facts["tell them"]


def test_a_credit_limit_written_while_choosing_the_card_is_prefilled_on_its_form(client, apply_flow, advice, monkeypatch):
    seen = {}

    async def read_fields(action, said):
        seen["said"] = said
        return {"requestedLimit": "300000"}

    monkeypatch.setattr(chat_module, "_read_apply_fields", read_fields)
    monkeypatch.setitem(apply_flow, "cards", [ProductCard("Gold Credit", "Cards", "credit card", apply_via="credit_card_apply")])
    advice["advice"] = advise_module.Advice(
        {"suggested products": [{"name": "Gold Credit"}]}, products=[{"name": "Gold Credit", "group": "Cards", "strength": "info"}],
        choices=["Gold Credit"], used="recommend", must={})

    async def classify(message, recent_turns=None, app_notes=None):
        return BankingService("app_actions", "credit_card_apply", None, {})

    monkeypatch.setattr(chat_module, "classify", classify)
    say(client, "I want a credit card with a 3 lakh limit")
    apply_flow["picked"] = 0
    _, result = say(client, "ok apply for it, limit 300000")
    assert result["payload"]["ui"]["route"] == "/apply_for_credit_card"
    assert result["payload"]["ui"]["prefill"] == {"requestedLimit": "300000"}
    assert seen["said"] == ["I want a credit card with a 3 lakh limit", "ok apply for it, limit 300000"]


def test_a_credit_card_named_in_a_request_the_classifier_took_for_the_debit_screen_opens_the_credit_screen(client, apply_flow, advice):
    apply_flow["cards"] = [ProductCard("Platinum Debit", "Cards", "debit card", apply_via="card_apply"),
                           ProductCard("Gold Credit", "Cards", "credit card", apply_via="credit_card_apply")]
    apply_flow["picked"] = 1                                    # the message names Gold Credit
    reply, result = say(client, "ami Gold Credit er jonno apply korbo")
    assert apply_flow["asked"][-1] == ["Platinum Debit", "Gold Credit"]         # the products of every apply screen
    assert result["type"] == "APP_ACTION" and result["payload"]["ui"]["route"] == "/apply_for_credit_card"
    assert result["payload"]["products"] == [{"name": "Gold Credit", "group": "Cards", "strength": "apply"}]
    assert "cardProduct" not in (result["payload"]["ui"]["prefill"] or {})


def test_a_reply_that_wants_to_apply_but_not_clearly_which_asks_again_and_the_next_answer_still_counts(client, apply_flow, advice, monkeypatch):
    async def wants(message, names):
        apply_flow["wants_asked"] = list(names)
        return True

    monkeypatch.setattr(chat_module, "_wants_to_apply", wants)
    say(client, "I want to apply for a debit card")
    apply_flow["picked"] = None
    _, asked = say(client, "ei jinish ta nite chai")                            # garbled: which one is unclear
    assert asked["type"] == "CLARIFICATION_REQUIRED" and apply_flow["wants_asked"] == ["Platinum Debit", "Gold Debit"]
    reply = say(client, "ei jinish ta nite chai")[0]
    assert "Platinum Debit" in reply and "Gold Debit" in reply
    apply_flow["picked"] = 1
    _, result = say(client, "the second")
    assert result["type"] == "APP_ACTION" and result["payload"]["products"][0]["name"] == "Gold Debit"


def test_a_reply_about_something_else_is_not_taken_for_an_application(client, apply_flow, advice, monkeypatch):
    async def wants(message, names):
        return False

    monkeypatch.setattr(chat_module, "_wants_to_apply", wants)
    say(client, "I want to apply for a debit card")
    apply_flow["picked"] = None
    before = apply_flow["classify_calls"]
    say(client, "what is the fee for a transfer?")
    assert apply_flow["classify_calls"] == before + 1


def test_the_model_must_quote_the_words_that_name_a_product_picked_from_a_first_message(monkeypatch):
    import asyncio

    asked = []

    async def post(path, body, **kw):
        asked.append(body["prompt"])
        return {"response": json.dumps({"choice": 2, "quote": quote["text"]})}

    monkeypatch.setattr(chat_module.llm_backend, "post", post)
    quote = {"text": "ইসলামিক ভিসা ইনফিনিটি"}
    names = ["Gold Credit", "Islamic Visa Infinite"]
    message = "আমি ইসলামিক ভিসা ইনফিনিটি টার জন্য এপ্লাই করব"
    assert asyncio.run(chat_module._llm_pick_name(message, names, offered=False)) == 1
    assert '"quote"' in asked[0] and "written in Bangla letters" in asked[0]
    quote["text"] = "words the customer never wrote"
    assert asyncio.run(chat_module._llm_pick_name(message, names, offered=False)) is None


def test_one_suggested_product_without_a_screen_or_a_mix_of_screens_no_longer_drops_the_offer_to_apply(client, apply_flow, advice):
    apply_flow["cards"] = [ProductCard("Platinum Debit", "Cards", "debit card", apply_via="card_apply"),
                           ProductCard("Gold Credit", "Cards", "credit card", apply_via="credit_card_apply"),
                           ProductCard("Corporate Card", "Cards", "corporate card")]            # no screen opens it
    advice["advice"] = advise_module.Advice(
        {"suggested products": [{"name": "Gold Credit"}]}, must={},
        products=[{"name": n, "group": "Cards", "strength": "info"} for n in ("Gold Credit", "Platinum Debit", "Corporate Card")],
        choices=["Gold Credit", "Platinum Debit", "Corporate Card"], used="recommend")
    say(client, "I want to apply for a card")                                      # the suggestion turn
    apply_flow["picked"] = 1                                                        # "the second one": Platinum Debit
    _, result = say(client, "the second one")
    assert result["type"] == "APP_ACTION" and result["payload"]["ui"]["route"] == "/request_virtual_card/form"
    assert result["payload"]["products"][0]["name"] == "Platinum Debit"
    apply_flow["picked"] = None
    say(client, "I want to apply for a card")
    apply_flow["picked"] = 0                                                        # "the first one": Gold Credit
    _, result = say(client, "the first one")
    assert result["payload"]["ui"]["route"] == "/apply_for_credit_card"             # that product's own screen


def test_an_answer_about_the_suggested_products_leaves_the_offer_to_apply_standing():
    pending = {"action": "card_apply", "choices": ["A", "B"], "screens": {"A": "card_apply", "B": "card_apply"}}
    kept = chat_module._with_pending_apply(chat_module._topic_classification("KB_ANSWER", ["A"]), {"pending_apply": pending})
    assert kept["pending_apply"] == pending and kept["type"] == "KB_ANSWER" and kept["topic"] == ["A"]
    assert chat_module._with_pending_apply(chat_module._topic_classification("KB_ANSWER", ["A"]), {}) == \
        chat_module._topic_classification("KB_ANSWER", ["A"])
    only_offer = chat_module._with_pending_apply(None, {"pending_apply": pending})
    assert only_offer["pending_apply"] == pending and only_offer["type"] == "KB_ANSWER"
