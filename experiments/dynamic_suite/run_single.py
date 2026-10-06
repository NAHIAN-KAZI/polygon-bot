"""Single-turn live suite: every row of INTENT_IMPLEMENTATION_STATUS.md x 5 question
styles, each in a fresh conversation, scored on the route and the reply.

  python -m experiments.dynamic_suite.run_single [--only 1.6,4.8] [--styles one_word,casual] [--through FEES]

Needs EVAL_USERNAME / EVAL_PASSWORD (EVAL_API_KEY defaults to the app's key). Nothing
is ever confirmed or submitted: a question that opens a change flow is dropped by the
next message. Report: experiments/results/dynamic/single_<time>.{jsonl,md}
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

os.environ.setdefault("EVAL_API_KEY", os.environ.get("API_KEY", ""))
from experiments.dynamic_suite.checks import judge, reply_flags  # noqa: E402
from experiments.live_freeze_test import chat, login  # noqa: E402

QUESTIONS = Path(__file__).with_name("questions.json")
OUT = Path(__file__).resolve().parents[1] / "results" / "dynamic"
_PENDING = ("CLARIFICATION_REQUIRED", "OTP_REQUIRED", "CONFIRMATION_REQUIRED", "ACCOUNT_SELECTION_REQUIRED",
            "TRANSACTION_SELECTION_REQUIRED", "BENEFICIARY_SELECTION_REQUIRED")


async def ask(client, state, message):
    """(reply, result, seconds); a transport failure is returned as an ERROR result so one
    bad request never stops the run."""
    start = time.monotonic()
    try:
        text, result = await chat(client, state["token"], message)
        if result.get("type") == "AUTH_REQUIRED":
            state["token"] = await login(client)
            text, result = await chat(client, state["token"], message)
    except (httpx.HTTPError, ValueError) as exc:
        text, result = "", {"type": "TRANSPORT_ERROR", "error": f"{exc.__class__.__name__}: {exc}"}
    return text, result, time.monotonic() - start


async def main():
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else set()
    styles = set(sys.argv[sys.argv.index("--styles") + 1].split(",")) if "--styles" in sys.argv else set()
    through = sys.argv[sys.argv.index("--through") + 1] if "--through" in sys.argv else None  # last intent to run, in doc order
    rows = json.loads(QUESTIONS.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    records, done = [], set()
    resume = Path(sys.argv[sys.argv.index("--resume") + 1]) if "--resume" in sys.argv else None
    if resume:
        records = [json.loads(line) for line in resume.read_text().splitlines() if line.strip()]
        done = {(r["row"], r["style"]) for r in records}
        stamp = resume.stem.removeprefix("single_")
    async with httpx.AsyncClient(timeout=60) as client:
        state = {"token": await login(client)}
        with open(OUT / f"single_{stamp}.jsonl", "a" if resume else "w") as log:
            finished = False
            for key, row in rows.items():
                if finished or (only and key not in only):
                    continue
                if through and any(r["intent"] == through for r in records) and row["intent"] != through:
                    finished = True  # first row after the last wanted intent
                    continue
                for style, question in row["questions"].items():
                    if (styles and style not in styles) or (key, style) in done:
                        continue
                    text, result, secs = await ask(client, state, question)
                    expected = tuple(row["expected"]) if isinstance(row["expected"], list) else row["expected"]
                    status, why = judge(expected, text, result)
                    flags = reply_flags(text, result.get("type") or "")
                    rec = {"row": key, "intent": row["intent"], "name": row["name"], "style": style,
                           "question": question, "reply": text, "type": result.get("type"),
                           "route": f'{result.get("category")}/{result.get("service")}/{result.get("subservice")}',
                           "status": status, "why": why, "flags": flags, "secs": round(secs, 1)}
                    records.append(rec)
                    log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    log.flush()
                    print(f"{status:11} {key:10} {style:9} {secs:4.1f}s {flags or ''} | {question[:60]!r} -> {text[:90]!r}", flush=True)
                    if result.get("type") in _PENDING:  # drop an open question / step; others need no reset
                        await ask(client, state, "ok thanks")
    write_report(records, OUT / f"single_{stamp}.md")


def write_report(records: list[dict], path: Path) -> None:
    from collections import Counter
    totals = Counter(r["status"] for r in records)
    lines = [f"# Single-turn live suite — {len(records)} questions", "",
             "Statuses: " + ", ".join(f"{k} {v}" for k, v in sorted(totals.items())), ""]
    flagged = Counter(f for r in records for f in r["flags"])
    if flagged:
        lines += ["Reply flags: " + ", ".join(f"{k} {v}" for k, v in flagged.most_common()), ""]
    by_style = {}
    for r in records:
        by_style.setdefault(r["style"], Counter())[r["status"]] += 1
    lines += ["| style | " + " | ".join(sorted(totals)) + " |", "|---|" + "---|" * len(totals)]
    for style, c in by_style.items():
        lines.append(f"| {style} | " + " | ".join(str(c.get(s, 0)) for s in sorted(totals)) + " |")
    lines += ["", "## Not passing, or flagged", ""]
    for r in records:
        if r["status"] != "PASS" or r["flags"]:
            lines += [f"**{r['row']} {r['name']}** · {r['style']} · {r['status']} ({r['why']}) {r['flags'] or ''}",
                      f"- Customer: {r['question']}", f"- Bot: {r['reply']}", f"- route: {r['type']} {r['route']}", ""]
    lines += ["## Everything", ""]
    for r in records:
        lines += [f"- {r['status']} · {r['row']} · {r['style']} · {r['question']!r} → {r['reply'][:200]!r}"]
    path.write_text("\n".join(lines))
    print(f"\nreport: {path}\n" + "\n".join(lines[:12]))


if __name__ == "__main__":
    asyncio.run(main())
