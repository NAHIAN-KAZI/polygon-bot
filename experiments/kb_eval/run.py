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
from pathlib import Path

from app.chunking import chunk_document
from app.config import settings
from app.embeddings import embed_texts

from experiments.kb_eval import harness
from experiments.kb_eval.harness import EmbeddingCache, Question

HERE = Path(__file__).parent


async def baseline(chunks, matrix, cache: EmbeddingCache, questions: list[Question]) -> list[list[int]]:
    """Production today: embed the message as typed and rank every chunk by cosine."""
    vectors = await cache.embed([q.text for q in questions], embed_texts)
    return [harness.cosine_order(v, matrix) for v in vectors]


STRATEGIES = {"baseline": baseline}


def _report(name: str, questions, ranks, chunks) -> tuple[str, dict]:
    stats = harness.summarise(ranks)
    lines = [f"### {name}", "",
             "| questions | recall@1 | recall@5 | recall@10 | recall@20 | MRR | median rank | not found |",
             "|---|---|---|---|---|---|---|---|",
             f"| {stats['questions']} | {stats['recall@1']:.0%} | {stats['recall@5']:.0%} | {stats['recall@10']:.0%} | "
             f"{stats['recall@20']:.0%} | {stats['mrr']:.3f} | {stats['median_rank']} | {stats['not_found']} |", ""]
    worst = sorted(zip(questions, ranks), key=lambda qr: -(qr[1] or 10**6))[:15]
    lines += ["Worst misses (rank of the first correct chunk):", ""]
    for question, rank in worst:
        if rank is not None and rank <= 5:
            continue
        lines.append(f"- {rank or 'not found'}: {question.text}")
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
        orders = await STRATEGIES[args.strategy](chunks, matrix, cache, questions)
        ranks = [harness.rank_of_first_match(order, chunks, q) for order, q in zip(orders, questions)]
        text, stats = _report(name, questions, ranks, chunks)
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
