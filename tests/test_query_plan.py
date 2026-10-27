import asyncio

from app.knowledge import catalogue, query_plan

CATALOGUE = [
    {"name": "Visa Infinite", "group": "Cards"},
    {"name": "Polygon Visa Debit Card", "group": "Cards"},
    {"name": "Personal Loan", "group": "Loans and finance"},
]


def test_catalogue_is_distinct_and_sorted_by_group_then_name():
    payloads = [{"product": "Personal Loan", "group": "Loans and finance"},
                {"product": "Visa Infinite", "group": "Cards"},
                {"product": "Visa Infinite", "group": "Cards"},
                {"product": None, "group": "Cards"},
                {"product": "Polygon Visa Debit Card", "group": "Cards"}]
    assert catalogue.distinct(payloads) == [CATALOGUE[1], CATALOGUE[0], CATALOGUE[2]]


def test_prompt_lists_the_catalogue_and_treats_the_message_as_data():
    prompt = query_plan.build_prompt("what about its fees?", ["tell me about Visa Infinite"], CATALOGUE)
    assert "1. Visa Infinite [Cards]" in prompt and "3. Personal Loan [Loans and finance]" in prompt
    assert "tell me about Visa Infinite" in prompt and "what about its fees?" in prompt
    assert "ignore them" in prompt


def test_valid_answer_is_kept_and_numbers_become_catalogue_names():
    raw = {"queries": ["credit card eligibility", "who can apply for a credit card"], "products": [1, 2],
           "group": "Cards"}
    plan = query_plan.parse(raw, "m", CATALOGUE)
    assert plan.queries == ["credit card eligibility", "who can apply for a credit card"]
    assert plan.products == ["Visa Infinite", "Polygon Visa Debit Card"] and plan.group == "Cards"


def test_bad_numbers_unknown_group_duplicates_and_extra_queries_are_dropped():
    raw = {"queries": ["a", "A", "b", "c", "d"], "products": [0, 4, True, "1", 3, 3], "group": "Made up"}
    plan = query_plan.parse(raw, "m", CATALOGUE)
    assert plan.queries == ["a", "b", "c"]  # case-insensitive duplicate dropped, at most three
    assert plan.products == ["Personal Loan"] and plan.group is None


def test_malformed_or_missing_answer_searches_for_the_message_as_typed():
    for raw in (None, {}, {"queries": "text"}, {"queries": [1, None, ""]}, ["list"]):
        plan = query_plan.parse(raw, "my message", CATALOGUE)
        assert plan.queries == ["my message"] and plan.products == [] and plan.group is None


def test_plan_falls_back_when_the_model_call_fails(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(query_plan.llm_backend, "post", boom)
    plan = asyncio.run(query_plan.plan("hello", [], CATALOGUE))
    assert plan.queries == ["hello"] and plan.products == []


def test_plan_sends_the_prompt_in_json_mode_and_reads_the_reply(monkeypatch):
    sent = {}

    async def fake_post(path, body, timeout=None):
        sent.update(path=path, body=body)
        return {"response": '{"queries": ["visa infinite fees"], "products": [1], "group": "Cards"}'}

    monkeypatch.setattr(query_plan.llm_backend, "post", fake_post)
    plan = asyncio.run(query_plan.plan("its fees?", ["Visa Infinite"], CATALOGUE))
    assert sent["path"] == "/api/generate" and sent["body"]["format"] == "json"
    assert sent["body"]["options"]["temperature"] == 0
    assert plan.queries == ["visa infinite fees"] and plan.products == ["Visa Infinite"]


def test_empty_catalogue_skips_the_model(monkeypatch):
    async def never(*a, **k):
        raise AssertionError("the model must not be called without a catalogue")

    monkeypatch.setattr(query_plan.llm_backend, "post", never)
    assert asyncio.run(query_plan.plan("hi", [], [])).queries == ["hi"]
