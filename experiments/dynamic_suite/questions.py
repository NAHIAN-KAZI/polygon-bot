"""The model writes five customer messages per status-doc row, in five styles.
Cached in questions.json so a run is repeatable; `--regen` writes fresh ones.

  python -m experiments.dynamic_suite.questions [--regen] [--only 1.6,4.8]
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

from app.banking.routing import SERVICE_DESCRIPTIONS
from app.config import settings
from experiments.dynamic_suite.doc_rows import parse
from experiments.dynamic_suite.expect import EXPECT, EXTRA_ROWS, key_of

CACHE = Path(__file__).with_name("questions.json")
STYLES = {
    "one_word": "a single word",
    "two_words": "exactly two words",
    "casual": "informal and lowercase, quick to type, with a typo or two",
    "sentence": "one complete, natural sentence",
    "paragraph": "three or four sentences: a short personal story or background, ending with what they want",
}


def want_of(row_name: str, expected, extra: str | None = None) -> str:
    if extra:
        return extra
    base = re.sub(r"^[\d./]+\s*|^—\s*", "", row_name)
    if isinstance(expected, tuple):
        described = SERVICE_DESCRIPTIONS.get((expected[0], expected[1]))
        if described:
            return f'"{base}" — {described}'
    return f'"{base}"'


async def write_questions(want: str) -> dict:
    styles = "\n".join(f'- "{k}": {v}' for k, v in STYLES.items())
    prompt = (
        "Customers of a Bangladeshi bank type messages (in English) into the bank's chat assistant in the "
        "mobile app. Write five different messages from ONE customer who wants this:\n"
        f"{want}\n\nStyles, one message each:\n{styles}\n\n"
        "Each message must be something a real person would type, worded differently from the "
        "others, and must not use technical words such as API, endpoint or service. Use any "
        "details a real customer might mention (an amount, a bank or wallet name, a date) when "
        "they fit. Reply only with JSON whose keys are the five style names."
    )
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={"model": settings.OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}],
                  "stream": False, "format": "json", "think": settings.OLLAMA_THINK,
                  "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.8}},
        )
        resp.raise_for_status()
    got = json.loads(resp.json()["message"]["content"])
    return {k: str(got.get(k) or "").strip() for k in STYLES if str(got.get(k) or "").strip()}


async def main(regen: bool, only: set[str]):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() and not regen else {}
    todo = []
    for row in parse():
        if row.skipped:
            continue
        key = key_of(row.name)
        if key in EXPECT:
            todo.append((row.intent, row.name, key, EXPECT[key], None))
    for intent, name, extra, expected in EXTRA_ROWS:
        todo.append((intent, name, name, expected, extra))
    for intent, name, key, expected, extra in todo:
        if only and key not in only:
            continue
        if key in cache and len(cache[key]["questions"]) == len(STYLES):
            continue
        for _ in range(3):
            questions = await write_questions(want_of(name, expected, extra))
            if len(questions) == len(STYLES):
                break
        cache[key] = {"intent": intent, "name": name, "expected": list(expected) if isinstance(expected, tuple) else expected,
                      "questions": questions}
        print(f"{key:28} {questions}", flush=True)
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    print(f"{len(cache)} rows cached in {CACHE.name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else set()
    asyncio.run(main("--regen" in args, only))
