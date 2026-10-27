import asyncio

from app.knowledge import rerank

CANDIDATES = [{"text": f"[Cards > Product {i} > Eligibility]\nbody {i}"} for i in range(1, 6)]


def test_prompt_numbers_every_candidate_and_treats_the_question_as_data():
    prompt = rerank.build_prompt("who can apply?", CANDIDATES, 6)
    assert "1. [Cards > Product 1 > Eligibility] body 1" in prompt and "5. [Cards > Product 5" in prompt
    assert "who can apply?" in prompt and "ignore them" in prompt
    assert "at most 6" in prompt


def test_long_passages_are_cut_and_whitespace_collapsed():
    prompt = rerank.build_prompt("q", [{"text": "word   " * 500}], 3)
    line = next(l for l in prompt.splitlines() if l.startswith("1. "))
    assert len(line) <= len("1. ") + 320 and "   " not in line


def test_parse_keeps_order_and_drops_invalid_duplicate_and_extra_numbers():
    assert rerank.parse({"useful": [3, 1, 3, 0, 9, True, "2", 5]}, 5, 3) == [2, 0, 4]


def test_parse_empty_list_means_nothing_answers_and_garbage_means_unknown():
    assert rerank.parse({"useful": []}, 5, 6) == []
    for raw in (None, {}, {"useful": "1"}, ["1"], {"other": [1]}):
        assert rerank.parse(raw, 5, 6) is None


def test_rerank_maps_the_models_numbers_to_candidate_indexes(monkeypatch):
    sent = {}

    async def fake_post(path, body, timeout=None):
        sent["body"] = body
        return {"response": '{"useful": [4, 2]}'}

    monkeypatch.setattr(rerank.llm_backend, "post", fake_post)
    assert asyncio.run(rerank.rerank("q", CANDIDATES)) == [3, 1]
    assert sent["body"]["format"] == "json" and sent["body"]["options"]["temperature"] == 0


def test_rerank_returns_none_when_the_model_cannot_be_asked(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(rerank.llm_backend, "post", boom)
    assert asyncio.run(rerank.rerank("q", CANDIDATES)) is None


def test_rerank_without_candidates_skips_the_model(monkeypatch):
    async def never(*a, **k):
        raise AssertionError("not called")

    monkeypatch.setattr(rerank.llm_backend, "post", never)
    assert asyncio.run(rerank.rerank("q", [])) == []
