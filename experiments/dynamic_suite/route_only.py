"""Offline routing check: every cached question goes through classify() alone, using the
saved service-list snapshot. No bank, no backend, no reply writing -- it measures only
whether the right service is picked, so prompts can be tuned while the bank is down.

  python -m experiments.dynamic_suite.route_only [--only 1.6,4.8] [--styles one_word,casual]

Report: experiments/results/dynamic/route_<time>.jsonl and a summary on stdout.
"""
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

import app.banking.taxonomy as taxonomy_module
from app.banking.routing import BankingService, Clarification, KbQuestion, UnknownService, classify
from experiments.dynamic_suite.checks import judge

QUESTIONS = Path(__file__).with_name("questions.json")
SNAPSHOT = Path(__file__).resolve().parents[1] / "results" / "taxonomy_snapshot.json"
OUT = Path(__file__).resolve().parents[1] / "results" / "dynamic"


def as_result(r) -> dict:
    if isinstance(r, BankingService):
        return {"type": "BANKING_SERVICE", "category": r.category, "service": r.service, "subservice": r.subservice}
    if isinstance(r, Clarification):
        return {"type": "CLARIFICATION_REQUIRED"}
    if isinstance(r, KbQuestion):
        return {"type": "KB_ANSWER"}
    if isinstance(r, UnknownService):
        return {"type": "UNKNOWN_SERVICE", "category": r.category, "service": r.service, "subservice": r.subservice}
    return {"type": repr(r)}


async def main():
    arg = lambda name: set(sys.argv[sys.argv.index(name) + 1].split(",")) if name in sys.argv else set()
    only, styles = arg("--only"), arg("--styles")
    cached = json.loads(SNAPSHOT.read_text())
    taxonomy_module._cache = cached
    taxonomy_module._index = taxonomy_module._build_index(cached["categories"])
    rows = json.loads(QUESTIONS.read_text())
    stamp = time.strftime("%Y%m%d_%H%M%S")
    records = []
    with open(OUT / f"route_{stamp}.jsonl", "w") as log:
        for key, row in rows.items():
            if only and key not in only:
                continue
            expected = tuple(row["expected"]) if isinstance(row["expected"], list) else row["expected"]
            for style, question in row["questions"].items():
                if styles and style not in styles:
                    continue
                result = as_result(await classify(question, []))
                # a transfer routed without its subservice is asked about by the chat, so it still counts
                status, why = judge(expected, "", result)
                rec = {"row": key, "name": row["name"], "style": style, "question": question,
                       "got": f'{result.get("type")} {result.get("category")}/{result.get("service")}/{result.get("subservice")}',
                       "status": status, "why": why}
                records.append(rec)
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()
                if status != "PASS":
                    print(f"{status:8} {key:8} {style:9} {question[:60]!r} -> {rec['got']}", flush=True)
    total = Counter(r["status"] for r in records)
    print(f"\n{len(records)} questions: {dict(total)}")
    by_style = {}
    for r in records:
        by_style.setdefault(r["style"], Counter())[r["status"]] += 1
    for style, c in by_style.items():
        print(f"  {style:10} {dict(c)}")


if __name__ == "__main__":
    asyncio.run(main())
