"""The knowledge answer path uses the planned search and its honest `grounded` (T-124, T-126, T-127)."""
import asyncio
import json
from datetime import datetime, timezone

import app.routes.chat as chat_module
from app.banking.routing import KbQuestion
from app.banking.session import ChatTurn
from app.knowledge import query_plan, retrieve

from tests.conftest import AUTH_HEADERS


def _turn(message):
    return ChatTurn(timestamp=datetime.now(timezone.utc), message=message, classification=None)


def _chat(client, monkeypatch, found, seen):
    async def classify(*a, **k):
        return KbQuestion()

    async def find(message, recent, top_k):
        seen.append((message, recent, top_k))
        return found

    async def stream(prompt):
        seen.append(("prompt", prompt))
        yield "answer"

    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "_find_knowledge", find)
    monkeypatch.setattr(chat_module, "stream_generate", stream)
    resp = client.post("/chat", json={"message": "what about its fees?", "top_k": 4}, headers=AUTH_HEADERS)
    for block in resp.text.strip("\n").split("\n\n"):
        if block.startswith("event: result"):
            return json.loads(block.split("data: ", 1)[1])
    return {}


def test_a_grounded_answer_reports_what_the_model_kept(client, monkeypatch):
    seen = []
    hits = [{"score": 0.8, "filename": "kb.md", "text": "fees are low", "product": "Visa", "group": "Cards"}]
    result = _chat(client, monkeypatch, retrieve.Retrieval(hits, True, query_plan.QueryPlan(["visa fees"]), True), seen)
    assert result["payload"]["grounded"] is True and result["payload"]["hitCount"] == 1
    assert result["payload"]["sources"] == ["kb.md"]
    assert seen[0][0] == "what about its fees?" and seen[0][2] == 4
    assert "fees are low" in next(x[1] for x in seen if x[0] == "prompt")


def test_when_the_model_kept_nothing_the_answer_is_not_grounded_and_has_no_sources(client, monkeypatch):
    seen = []
    result = _chat(client, monkeypatch, retrieve.Retrieval([], False, query_plan.QueryPlan(["x"]), True), seen)
    assert result["payload"] == {"grounded": False, "hitCount": 0, "sources": None}
    assert "fees are low" not in next(x[1] for x in seen if x[0] == "prompt")  # the no-information prompt


def test_recent_customer_messages_are_the_last_two_and_skip_redacted_ones():
    turns = [_turn("one"), _turn("[redacted: verification submission]"), _turn("two"), _turn("three"), _turn("")]
    assert chat_module._recent_customer_messages(turns) == ["three"]
    assert chat_module._recent_customer_messages([_turn("a"), _turn("b"), _turn("c")]) == ["b", "c"]
    assert chat_module._recent_customer_messages(None) == []


def test_the_switch_off_searches_the_message_as_typed(monkeypatch):
    calls = []

    async def embed(text):
        calls.append(("embed", text))
        return [0.1]

    def search(vector, top_k):
        calls.append(("search", top_k))
        return [{"score": 0.9, "text": "t", "filename": "f"}]

    async def planned(*a, **k):
        raise AssertionError("the planned path must be off")

    monkeypatch.setattr(chat_module.settings, "KB_QUERY_PLANNING", False)
    monkeypatch.setattr(chat_module, "embed_text", embed)
    monkeypatch.setattr(chat_module, "search", search)
    monkeypatch.setattr(chat_module.knowledge_retrieve, "retrieve", planned)
    found = asyncio.run(chat_module._find_knowledge("hello", ["earlier"], None))
    assert calls == [("embed", "hello"), ("search", chat_module.settings.DEFAULT_TOP_K)]
    assert found.grounded is True and found.plan.queries == ["hello"] and found.reranked is False


def test_the_switch_on_uses_the_planned_path(monkeypatch):
    async def planned(message, recent, keep):
        return retrieve.Retrieval([], False, query_plan.QueryPlan([message]), True)

    monkeypatch.setattr(chat_module.settings, "KB_QUERY_PLANNING", True)
    monkeypatch.setattr(chat_module.knowledge_retrieve, "retrieve", planned)
    assert asyncio.run(chat_module._find_knowledge("hello", [], 3)).reranked is True


def test_the_log_line_carries_counts_not_the_planned_query_text(client, monkeypatch, caplog):
    import logging
    secret = "account 1234567890123"
    found = retrieve.Retrieval([], False, query_plan.QueryPlan([secret, "more"], ["P"]), True)
    with caplog.at_level(logging.INFO):
        _chat(client, monkeypatch, found, [])
    line = next(r.getMessage() for r in caplog.records if '"planned_queries"' in r.getMessage())
    assert '"planned_queries": 2' in line and '"planned_products": 1' in line
    assert "1234567890123" not in line


def _chat_as(client, monkeypatch, classified, headers=None):
    async def classify(*a, **k):
        return classified

    async def find(message, recent, top_k):
        return retrieve.Retrieval([{"score": 0.8, "filename": "kb.md", "text": "we offer cards", "product": "Visa",
                                    "group": "Cards"}], True, query_plan.QueryPlan([message]), True)

    async def stream(prompt):
        yield "answer"

    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "_find_knowledge", find)
    monkeypatch.setattr(chat_module, "stream_generate", stream)
    resp = client.post("/chat", json={"message": "which credit cards do you offer?"}, headers=headers or AUTH_HEADERS)
    return [json.loads(b.split("data: ", 1)[1]) for b in resp.text.strip("\n").split("\n\n") if b.startswith("event: result")]


def test_signed_out_a_question_about_what_the_bank_offers_is_answered_from_the_knowledge_base(client, monkeypatch):
    from app.banking.routing import BankingService
    results = _chat_as(client, monkeypatch, BankingService("card_info", "card_products", None, {}))
    assert [r["type"] for r in results] == ["KB_ANSWER"] and results[0]["payload"]["grounded"] is True


def test_signed_out_a_service_with_personal_data_still_asks_for_login(client, monkeypatch):
    from app.banking.routing import BankingService
    results = _chat_as(client, monkeypatch, BankingService("account_info", "balance", None, {}))
    assert [r["type"] for r in results] == ["AUTH_REQUIRED"]


def test_signed_in_too_what_the_bank_offers_is_answered_from_the_knowledge_base(client, monkeypatch):
    from app.banking.routing import BankingService
    from app.banking.identity import CustomerIdentity

    async def verify_jwt(token):
        return CustomerIdentity(customer_id="cust-catalogue")

    async def never(*a, **k):
        raise AssertionError("the bank's own catalogue must not be called")

    monkeypatch.setattr(chat_module, "verify_jwt", verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", never)
    results = _chat_as(client, monkeypatch, BankingService("card_info", "card_products", None, {}),
                       headers={**AUTH_HEADERS, "Authorization": "Bearer sometoken"})
    assert [r["type"] for r in results] == ["KB_ANSWER"] and results[0]["payload"]["grounded"] is True


def test_the_switch_for_that_use_case_still_applies_to_the_knowledge_route(client, monkeypatch):
    from app.banking.routing import BankingService

    async def classify(*a, **k):
        return BankingService("card_info", "card_products", None, {})

    monkeypatch.setattr(chat_module, "classify", classify)
    resp = client.post("/chat", json={"message": "which cards do you offer?", "disabled_use_cases": ["card_info.card_products"]},
                       headers=AUTH_HEADERS)
    types = [json.loads(b.split("data: ", 1)[1])["type"] for b in resp.text.strip("\n").split("\n\n") if b.startswith("event: result")]
    assert types == ["USE_CASE_DISABLED"]
