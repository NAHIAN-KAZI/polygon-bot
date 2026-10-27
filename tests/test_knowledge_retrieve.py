import asyncio

import pytest

from app.knowledge import query_plan, rerank, retrieve


def _hit(i, score, product="P"):
    return {"id": f"id{i}", "score": score, "text": f"text {i}", "product": product, "filename": "f.md"}


@pytest.fixture
def wired(monkeypatch):
    """The planner, embedder, vector store and reranker faked; returns the state the fakes record."""
    state = {"searches": [], "plan": query_plan.QueryPlan(["q1"], [], None), "picked": [0]}

    async def fake_plan(message, recent, cat):
        state["plan_args"] = (message, recent, cat)
        return state["plan"]

    async def fake_embed(texts):
        return [[float(i)] for i, _ in enumerate(texts)]

    def fake_search(vector, limit, products=None):
        state["searches"].append((vector, limit, products))
        return state["results"](vector, products)

    async def fake_rerank(question, pool, keep=6):
        state["pool"] = pool
        state["keep"] = keep
        return state["picked"]

    monkeypatch.setattr(retrieve.query_plan, "plan", fake_plan)
    monkeypatch.setattr(retrieve, "embed_texts", fake_embed)
    monkeypatch.setattr(retrieve.vectorstore, "search_in", fake_search)
    monkeypatch.setattr(retrieve.catalogue, "load", lambda: [{"name": "P", "group": "G"}])
    monkeypatch.setattr(retrieve.rerank, "rerank", fake_rerank)
    state["results"] = lambda vector, products: [_hit(int(vector[0]) * 100 + n, 0.9 - n / 100) for n in range(40)]
    return state


def test_every_text_searches_the_whole_index_and_the_plan_gets_the_catalogue_and_recent_words(wired):
    wired["plan"] = query_plan.QueryPlan(["a", "b"], [], None)
    asyncio.run(retrieve.retrieve("hello", ["earlier"], 4))
    assert [s[2] for s in wired["searches"]] == [None, None, None]  # message + two planned queries, no filter
    assert wired["plan_args"] == ("hello", ["earlier"], [{"name": "P", "group": "G"}])
    assert wired["keep"] == 4 and all(s[1] == retrieve.SEARCH_DEPTH for s in wired["searches"])


def test_named_products_add_a_filtered_search_per_text(wired):
    wired["plan"] = query_plan.QueryPlan(["a"], ["P"], None)
    asyncio.run(retrieve.retrieve("hello", [], None))
    assert [s[2] for s in wired["searches"]] == [None, None, ["P"], ["P"]]
    assert wired["keep"] == retrieve.DEFAULT_KEEP


def test_the_pool_keeps_the_plain_searchs_top_ten_then_fills_to_thirty_without_duplicates(wired):
    wired["plan"] = query_plan.QueryPlan(["a"], [], None)
    asyncio.run(retrieve.retrieve("hello", [], None))
    ids = [h["id"] for h in wired["pool"]]
    assert ids[:10] == [f"id{n}" for n in range(10)]  # the message's own top ten (vector 0) come first, in order
    assert len(ids) == retrieve.POOL_SIZE and len(set(ids)) == len(ids)


def test_the_model_decides_which_passages_are_kept_and_in_what_order(wired):
    wired["picked"] = [2, 0]
    found = asyncio.run(retrieve.retrieve("hello", [], None))
    assert [h["id"] for h in found.hits] == [wired["pool"][2]["id"], wired["pool"][0]["id"]]
    assert found.grounded and found.reranked


def test_when_no_passage_answers_the_result_is_not_grounded(wired):
    wired["picked"] = []
    found = asyncio.run(retrieve.retrieve("hello", [], None))
    assert found.hits == [] and found.grounded is False and found.reranked is True


def test_when_the_model_cannot_be_asked_the_plain_search_above_the_score_floor_is_used(wired, monkeypatch):
    wired["picked"] = None
    monkeypatch.setattr(retrieve.settings, "MIN_RELEVANCE_SCORE", 0.85)
    found = asyncio.run(retrieve.retrieve("hello", [], 3))
    assert [h["id"] for h in found.hits] == ["id0", "id1", "id2"] and found.grounded and not found.reranked


def test_fallback_with_nothing_above_the_floor_is_not_grounded(wired, monkeypatch):
    wired["picked"] = None
    monkeypatch.setattr(retrieve.settings, "MIN_RELEVANCE_SCORE", 0.99)
    found = asyncio.run(retrieve.retrieve("hello", [], None))
    assert found.hits == [] and found.grounded is False


def test_an_empty_index_gives_nothing_without_asking_the_model(wired, monkeypatch):
    wired["results"] = lambda vector, products: []

    async def never(*a, **k):
        raise AssertionError("rerank must not run on an empty pool")

    monkeypatch.setattr(retrieve.rerank, "rerank", never)
    found = asyncio.run(retrieve.retrieve("hello", [], None))
    assert found.hits == [] and found.grounded is False


def test_embedding_or_store_errors_reach_the_caller(wired, monkeypatch):
    def boom(vector, limit, products=None):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(retrieve.vectorstore, "search_in", boom)
    with pytest.raises(RuntimeError):
        asyncio.run(retrieve.retrieve("hello", [], None))


def test_when_nothing_answers_the_three_nearest_passages_are_kept_for_a_related_reply(wired):
    wired["picked"] = []
    found = asyncio.run(retrieve.retrieve("hello", [], None))
    assert found.hits == [] and found.grounded is False
    assert [h["id"] for h in found.nearest] == [h["id"] for h in wired["pool"][:retrieve.NEAREST_SHOWN]]


def test_an_answered_question_or_a_model_that_could_not_be_asked_has_no_nearest(wired):
    assert asyncio.run(retrieve.retrieve("hello", [], None)).nearest == []
    wired["picked"] = None
    assert asyncio.run(retrieve.retrieve("hello", [], None)).nearest == []
