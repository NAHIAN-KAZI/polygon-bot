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

    async def advise(message, recent, snap, need, cards):
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
