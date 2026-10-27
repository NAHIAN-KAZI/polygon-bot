import asyncio
from types import SimpleNamespace

import numpy as np

from experiments.kb_eval import harness
from experiments.kb_eval.harness import EmbeddingCache, Question


def _chunk(*path):
    return SimpleNamespace(heading_path=list(path))


CHUNKS = [
    _chunk("Cards", "Visa Debit Card", "Eligibility"),
    _chunk("Cards", "Visa Infinite", "Who are eligible to apply for Visa Infinite Credit Card?"),
    _chunk("Help", "FAQ", "Who are eligible to apply for Visa Infinite Credit Card?"),
    _chunk("Loans", "Personal Loan", "Fees"),
    _chunk("Cards", "Overview"),
    _chunk(),
]


def test_a_chunk_matches_when_all_substrings_of_one_group_are_in_its_heading_path():
    q = Question("x", (("credit card", "eligib"), ("personal loan",)))
    assert harness.matches(CHUNKS[1], q)
    assert harness.matches(CHUNKS[3], q)
    assert not harness.matches(CHUNKS[0], q)  # debit card: 'eligib' but not 'credit card'


def test_faq_questions_take_each_question_heading_once_and_either_copy_answers_it():
    questions = harness.faq_questions(CHUNKS)
    assert [q.text for q in questions] == ["Who are eligible to apply for Visa Infinite Credit Card?"]
    assert harness.matches(CHUNKS[1], questions[0]) and harness.matches(CHUNKS[2], questions[0])
    assert not harness.matches(CHUNKS[0], questions[0])


def test_rank_is_one_based_and_none_when_no_chunk_matches():
    q = Question("x", (("fees",),))
    assert harness.rank_of_first_match([0, 1, 3], CHUNKS, q) == 3
    assert harness.rank_of_first_match([0, 1, 2], CHUNKS, q) is None


def test_summary_counts_recall_mrr_and_misses():
    stats = harness.summarise([1, 4, 12, None])
    assert stats["recall@1"] == 0.25 and stats["recall@5"] == 0.5 and stats["recall@20"] == 0.75
    assert stats["not_found"] == 1 and stats["median_rank"] == 4
    assert abs(stats["mrr"] - (1 + 1 / 4 + 1 / 12) / 4) < 1e-9


def test_cosine_order_ranks_the_closest_vector_first():
    matrix = np.array([[0.0, 1.0], [1.0, 0.0], [0.7, 0.7]], dtype=np.float32)
    assert harness.cosine_order(np.array([1.0, 0.1], dtype=np.float32), matrix) == [1, 2, 0]


def test_embedding_cache_embeds_each_text_once_and_normalises(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "CACHE_DIR", tmp_path)
    calls = []

    async def fake_embed(texts):
        calls.append(list(texts))
        return [[3.0, 4.0] for _ in texts]

    cache = EmbeddingCache("model/x")
    first = asyncio.run(cache.embed(["a", "b", "a"], fake_embed))
    second = asyncio.run(EmbeddingCache("model/x").embed(["a", "b"], fake_embed))
    assert calls == [["a", "b"]]  # duplicates sent once, the second run read the file
    assert np.allclose(first[0], [0.6, 0.8]) and np.allclose(second[1], [0.6, 0.8])
