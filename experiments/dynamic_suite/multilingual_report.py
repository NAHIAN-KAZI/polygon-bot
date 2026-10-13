"""Markdown for the "Bangla, Banglish and voice" section of
planning/reports/INTENT_USE_CASE_COVERAGE.md, built from the latest multilingual text run
(route_only --questions questions_multilingual.json) and the latest voice run (voice_route).

  python -m experiments.dynamic_suite.multilingual_report [--text route_X.jsonl] [--voice voice_Y.jsonl]
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = Path(__file__).resolve().parents[1] / "results" / "dynamic"
TEXT_STYLES = ["bangla_short", "bangla_sentence", "banglish_short", "banglish_sentence", "mixed"]
VOICE_STYLES = ["bangla_sentence", "mixed", "sentence"]
STYLE_NAMES = {
    "bangla_short": "Bangla, short", "bangla_sentence": "Bangla, sentence", "banglish_short": "Banglish, short",
    "banglish_sentence": "Banglish, sentence", "mixed": "Mixed Bangla-English", "sentence": "English",
}
MARK = {"PASS": "✅", "CLARIFY": "❓", "FAIL": "❌", "UNAVAILABLE": "⚠️", "ERROR": "⚠️"}


def latest(prefix: str, must_have_style: str) -> Path:
    for path in sorted(RESULTS.glob(f"{prefix}_*.jsonl"), reverse=True):
        first = path.open().readline()
        if first and json.loads(first)["style"] in (TEXT_STYLES if prefix == "route" else VOICE_STYLES):
            if must_have_style in path.read_text():
                return path
    raise SystemExit(f"no {prefix} run found")


def load(path: Path) -> dict:
    return {(r["row"], r["style"]): r for r in map(json.loads, path.open())}


def tally(records, styles) -> str:
    rows = ["| Style | Questions | Routed right | Asked a question | Wrong service | Other |", "|---|---|---|---|---|---|"]
    total = Counter()
    for style in styles:
        c = Counter(r["status"] for r in records if r["style"] == style)
        n = sum(c.values())
        total += c
        other = n - c["PASS"] - c["CLARIFY"] - c["FAIL"]
        rows.append(f"| {STYLE_NAMES[style]} | {n} | {c['PASS']} | {c['CLARIFY']} | {c['FAIL']} | {other} |")
    n = sum(total.values())
    rows.append(f"| **All** | **{n}** | **{total['PASS']} ({100 * total['PASS'] // max(n, 1)}%)** | **{total['CLARIFY']}** "
                f"| **{total['FAIL']}** | **{n - total['PASS'] - total['CLARIFY'] - total['FAIL']}** |")
    return "\n".join(rows)


def main():
    arg = lambda name: Path(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else None
    text_path = arg("--text") or latest("route", "banglish_short")
    voice_path = arg("--voice") or latest("voice", "bangla_sentence")
    text, voice = load(text_path), load(voice_path)
    questions = json.loads((HERE / "questions_multilingual.json").read_text())

    out = [f"Text run: `{text_path.name}`. Voice run: `{voice_path.name}`.\n",
           "**Typed messages (Bangla script, Banglish, mixed)**\n", tally(text.values(), TEXT_STYLES), "",
           "**Spoken messages** (synthetic neural voices; transcribed by the app, then routed)\n",
           tally(voice.values(), VOICE_STYLES), "",
           "Per use case below: one example message per style, then the result for each style "
           "(✅ routed right, ❓ asked a question, ❌ wrong service, ⚠️ error). Typed: Bangla short, Bangla "
           "sentence, Banglish short, Banglish sentence, mixed. Spoken: Bangla, mixed, English.\n"]
    by_intent = defaultdict(list)
    for key, row in questions.items():
        by_intent[row["intent"]].append((key, row))
    for intent, rows in by_intent.items():
        out += [f"#### {intent}\n", "| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |", "|---|---|---|---|---|---|---|"]
        for key, row in rows:
            q = row["questions"]
            typed = "".join(MARK.get(text.get((key, s), {}).get("status"), "·") for s in TEXT_STYLES)
            spoken = "".join(MARK.get(voice.get((key, s), {}).get("status"), "·") for s in VOICE_STYLES)
            name = row["name"].split(" ", 1)[1] if row["name"][0].isdigit() else row["name"]
            cell = lambda s: q.get(s, "").replace("|", "/")
            out.append(f"| {key if key[0].isdigit() else ''} | {name} | {cell('bangla_sentence')} | {cell('banglish_short')} "
                       f"| {cell('mixed')} | {typed} | {spoken} |")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main()
