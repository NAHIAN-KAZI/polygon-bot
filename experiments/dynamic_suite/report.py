"""Full per-case markdown report from a run_single .jsonl:
every question, the bot's whole reply, the route it took, the verdict and any flags,
grouped by intent and status-doc row.

  python -m experiments.dynamic_suite.report [experiments/results/dynamic/single_<time>.jsonl]
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results" / "dynamic"
STYLE_ORDER = ["one_word", "two_words", "casual", "sentence", "paragraph"]
ICON = {"PASS": "✅", "CLARIFY": "❓", "UNAVAILABLE": "🔌", "FAIL": "❌", "ERROR": "⚠️"}


def build(records: list[dict], source: str) -> str:
    totals = Counter(r["status"] for r in records)
    flagged = Counter(f for r in records for f in r["flags"])
    lines = ["# Single-turn live suite — every case", "",
             f"Source: `{source}` · {len(records)} questions · "
             + " · ".join(f"{ICON.get(k, '')} {k} {v}" for k, v in sorted(totals.items())), ""]
    if flagged:
        lines += ["Reply flags: " + ", ".join(f"{k} {v}" for k, v in flagged.most_common()), ""]
    lines += ["Statuses: ✅ PASS = routed as expected (or correctly declined) · ❓ CLARIFY = asked a question "
              "instead of routing · 🔌 UNAVAILABLE = right service, the bank call failed · ❌ FAIL = wrong route "
              "or claimed something it shouldn't · ⚠️ ERROR = infrastructure (auth/empty). "
              "Questions are written by a model, so a ❌ can be a drifted question — read each one.", ""]
    by_intent = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_intent[r["intent"]][(r["row"], r["name"])].append(r)
    lines += ["## Summary by intent", "", "| intent | questions | ✅ | ❓ | ❌ | 🔌 | ⚠️ |", "|---|---|---|---|---|---|---|"]
    for intent, rows in by_intent.items():
        c = Counter(r["status"] for rs in rows.values() for r in rs)
        n = sum(c.values())
        lines.append(f"| {intent} | {n} | {c['PASS']} | {c['CLARIFY']} | {c['FAIL']} | {c['UNAVAILABLE']} | {c['ERROR']} |")
    lines.append("")
    for intent, rows in by_intent.items():
        lines += [f"## {intent}", ""]
        for (key, name), rs in rows.items():
            c = Counter(r["status"] for r in rs)
            counts = " ".join(ICON.get(k, "") + str(v) for k, v in sorted(c.items()))
            lines += [f"### {name}  ({counts})", ""]
            for r in sorted(rs, key=lambda r: STYLE_ORDER.index(r["style"]) if r["style"] in STYLE_ORDER else 9):
                why = f" — {r['why']}" if r["status"] != "PASS" else ""
                flags = f" · flags: {', '.join(r['flags'])}" if r["flags"] else ""
                reply = r["reply"].strip().replace("\n", "\n  > ")
                lines += [f"- {ICON.get(r['status'], '')} **{r['style']}** ({r['secs']}s){why}{flags}",
                          f"  - Customer: {r['question']}",
                          f"  - Bot: {reply}",
                          f"  - Route: `{r['type']}` · `{r['route']}`", ""]
    return "\n".join(lines)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(RESULTS.glob("single_*.jsonl"))[-1]
    records = [json.loads(line) for line in src.read_text().splitlines() if line.strip()]
    out = src.with_name(src.stem + "_full.md")
    out.write_text(build(records, src.name))
    print(f"{out}  ({len(records)} cases)")


if __name__ == "__main__":
    main()
