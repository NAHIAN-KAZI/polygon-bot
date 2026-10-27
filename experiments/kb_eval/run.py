"""Run the retrieval evaluation (T-123).

    OLLAMA_BASE_URL=http://192.168.12.41:11434 python -m experiments.kb_eval.run \
        --file planning/knowledge_base/POLYGON_BANK_KNOWLEDGE_BASE_POLYGON.md [--strategy baseline] \
        [--min-recall5-faq 0.9] [--min-recall5-generic 0.8]

Prints recall@k, MRR and the median rank for the FAQ set (named-product questions) and the generic set, lists the
worst misses, and writes experiments/kb_eval/results/<strategy>.md. The exit code is 1 when a --min-recall5-* floor
is not met, so the run can guard retrieval against regressions.
"""
import argparse
import asyncio
import json
from pathlib import Path

import numpy as np

from app.chunking import chunk_document
from app.config import settings
from app.embeddings import embed_texts
from app.knowledge import catalogue as knowledge_catalogue
from app.knowledge import query_plan, rerank as knowledge_rerank

from experiments.kb_eval import harness
from experiments.kb_eval.harness import EmbeddingCache, Question

HERE = Path(__file__).parent


async def baseline(chunks, matrix, cache: EmbeddingCache, questions: list[Question]):
    """Production before T-124: embed the message as typed and rank every chunk by cosine."""
    vectors = await cache.embed([q.text for q in questions], embed_texts)
    return [harness.cosine_order(v, matrix) for v in vectors], [""] * len(questions)


async def _plans(questions: list[Question], catalogue: list[dict]) -> list[query_plan.QueryPlan]:
    """The model's plan for each question, cached by the exact prompt so a change to the prompt re-asks the model."""
    path = harness.CACHE_DIR / "plans.json"
    cached = json.loads(path.read_text()) if path.exists() else {}
    gate = asyncio.Semaphore(4)

    async def one(question: Question) -> query_plan.QueryPlan:
        key = harness._key(query_plan.build_prompt(question.text, [], catalogue))
        if key not in cached:
            async with gate:
                made = await query_plan.plan(question.text, [], catalogue)
            cached[key] = {"queries": made.queries, "products": made.products, "group": made.group}
        return query_plan.QueryPlan(**cached[key])

    plans = await asyncio.gather(*(one(q) for q in questions))
    harness.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cached))
    return plans


def _inside(plan: query_plan.QueryPlan, chunks) -> np.ndarray:
    if plan.products:
        return np.array([c.product in plan.products for c in chunks])
    if plan.group:
        return np.array([c.group == plan.group for c in chunks])
    return np.zeros(len(chunks), dtype=bool)


def _note(p: query_plan.QueryPlan) -> str:
    return f"queries={p.queries} products={p.products[:6]}{'...' if len(p.products) > 6 else ''} group={p.group}"


async def planned(chunks, matrix, cache: EmbeddingCache, questions: list[Question]):
    """T-124 as first tried: the planned queries, hard-narrowed to the products or group the model names."""
    plans = await _plans(questions, knowledge_catalogue.distinct({"product": c.product, "group": c.group} for c in chunks))
    texts = [t for p in plans for t in p.queries]
    by_text = dict(zip(texts, await cache.embed(texts, embed_texts)))
    orders = []
    for p in plans:
        scores = np.max([matrix @ by_text[t] for t in p.queries], axis=0)
        inside = _inside(p, chunks)
        orders.append(sorted(range(len(chunks)), key=lambda i: (not inside[i], -scores[i])))
    return orders, [_note(p) for p in plans]


RRF_K = 60


def _ranks(scores: np.ndarray) -> np.ndarray:
    ranks = np.empty(len(scores), dtype=np.int64)
    ranks[np.argsort(-scores)] = np.arange(1, len(scores) + 1)
    return ranks


async def fused(chunks, matrix, cache: EmbeddingCache, questions: list[Question], own_weight: float = 1.0,
                boost: float = 1.0):
    """The message as typed and the model's queries all search the whole index; reciprocal-rank fusion merges them,
    and chunks of the products the model names get one more vote, so a wrong plan costs a boost, not the answer.
    `own_weight` is how many votes the customer's own words get against one for each planned query."""
    plans = await _plans(questions, knowledge_catalogue.distinct({"product": c.product, "group": c.group} for c in chunks))
    texts = [t for q, p in zip(questions, plans) for t in [q.text, *p.queries]]
    by_text = dict(zip(texts, await cache.embed(texts, embed_texts)))
    orders = []
    for q, p in zip(questions, plans):
        votes = np.zeros(len(chunks))
        for text in dict.fromkeys([q.text, *p.queries]):
            votes += (own_weight if text == q.text else 1.0) / (RRF_K + _ranks(matrix @ by_text[text]))
        inside = _inside(p, chunks)
        if inside.any():
            combined = np.max([matrix @ by_text[t] for t in [q.text, *p.queries]], axis=0)
            filtered = np.where(inside, combined, -np.inf)
            votes += np.where(inside, boost / (RRF_K + _ranks(filtered)), 0.0)
        orders.append(list(np.argsort(-votes)))
    return orders, [_note(p) for p in plans]


POOL_OWN, POOL_FUSED = 10, 30


async def _rerank_cached(question: str, candidates: list[dict]) -> list[int] | None:
    path = harness.CACHE_DIR / "rerank.json"
    cached = json.loads(path.read_text()) if path.exists() else {}
    key = harness._key(knowledge_rerank.build_prompt(question, candidates, 6))
    if key not in cached:
        cached[key] = await knowledge_rerank.rerank(question, candidates)
        harness.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached))
    return cached[key]


async def reranked(chunks, matrix, cache: EmbeddingCache, questions: list[Question]):
    """T-124 + T-126: candidates = the plain search's top 10 plus the fused top of the planned search, 30 in all; the
    model keeps the ones that answer the question, best first; the rest of the candidates and the index follow."""
    base_orders, _ = await baseline(chunks, matrix, cache, questions)
    fused_orders, notes = await fused(chunks, matrix, cache, questions, own_weight=2.0, boost=1.0)
    gate = asyncio.Semaphore(4)
    orders, out_notes = [], []

    async def one(question, base, merged):
        pool = list(dict.fromkeys([*base[:POOL_OWN], *merged]))[:POOL_FUSED]
        async with gate:
            picked = await _rerank_cached(question.text, [{"text": chunks[i].text} for i in pool])
        head = [pool[j] for j in (picked or [])]
        rest = [i for i in pool if i not in head]
        tail = [i for i in merged if i not in head and i not in rest]
        return head + rest + tail, ("" if picked is None else f"model kept {len(picked)} of {len(pool)}")

    results = await asyncio.gather(*(one(q, b, m) for q, b, m in zip(questions, base_orders, fused_orders)))
    for (order, note), plan_note in zip(results, notes):
        orders.append(order)
        out_notes.append(f"{note} | {plan_note}")
    return orders, out_notes


STRATEGIES = {"baseline": baseline, "plan": planned, "fused": fused, "rerank": reranked}


def _report(name: str, questions, ranks, notes) -> tuple[str, dict]:
    stats = harness.summarise(ranks)
    lines = [f"### {name}", "",
             "| questions | recall@1 | recall@5 | recall@10 | recall@20 | recall@30 | MRR | median rank | not found |",
             "|---|---|---|---|---|---|---|---|---|",
             f"| {stats['questions']} | {stats['recall@1']:.0%} | {stats['recall@5']:.0%} | {stats['recall@10']:.0%} | "
             f"{stats['recall@20']:.0%} | {stats['recall@30']:.0%} | {stats['mrr']:.3f} | {stats['median_rank']} | "
             f"{stats['not_found']} |", ""]
    worst = sorted(zip(questions, ranks, notes), key=lambda t: -(t[1] or 10**6))[:15]
    lines += ["Worst misses (rank of the first correct chunk):", ""]
    for question, rank, note in worst:
        if rank is not None and rank <= 5:
            continue
        lines.append(f"- {rank or 'not found'}: {question.text}" + (f"\n  plan: {note}" if note else ""))
    return "\n".join(lines) + "\n", stats


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--strategy", default="baseline", choices=sorted(STRATEGIES))
    parser.add_argument("--min-recall5-faq", type=float, default=0.0)
    parser.add_argument("--min-recall5-generic", type=float, default=0.0)
    args = parser.parse_args()

    path = Path(args.file)
    chunks = chunk_document(path.name, path.read_bytes())
    cache = EmbeddingCache(settings.OLLAMA_EMBED_MODEL)
    matrix = await cache.embed([c.text for c in chunks], embed_texts)

    sets = {"FAQ questions (named product)": harness.faq_questions(chunks),
            "Generic questions": harness.load_generic(HERE / "generic_questions.json")}
    report = [f"# Retrieval evaluation: {args.strategy}", "",
              f"File `{path.name}`, {len(chunks)} chunks, embedding model `{settings.OLLAMA_EMBED_MODEL}`.", ""]
    floors = {"FAQ questions (named product)": args.min_recall5_faq, "Generic questions": args.min_recall5_generic}
    failed = False
    for name, questions in sets.items():
        unanswerable = [q.text for q in questions if not any(harness.matches(c, q) for c in chunks)]
        for text in unanswerable:
            print(f"  oracle matches no chunk (fix the question set): {text}")
        questions = [q for q in questions if q.text not in unanswerable]
        orders, notes = await STRATEGIES[args.strategy](chunks, matrix, cache, questions)
        ranks = [harness.rank_of_first_match(order, chunks, q) for order, q in zip(orders, questions)]
        text, stats = _report(name, questions, ranks, notes)
        report.append(text)
        print(text)
        if stats["recall@5"] < floors[name]:
            print(f"FAIL: {name} recall@5 {stats['recall@5']:.0%} is below {floors[name]:.0%}")
            failed = True
    out = HERE / "results" / f"{args.strategy}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(report), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
