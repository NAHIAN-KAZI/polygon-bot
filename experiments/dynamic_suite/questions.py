"""The model writes five customer messages per status-doc row, in five styles.
Cached in questions.json so a run is repeatable; `--regen` writes fresh ones.
`--multilingual` writes five more per row in Bangla script, Banglish (romanized Bangla)
and mixed Bangla-English, cached separately in questions_multilingual.json.

  python -m experiments.dynamic_suite.questions [--regen] [--multilingual] [--only 1.6,4.8]
"""
import asyncio
import json
import re
import sys
from pathlib import Path

from app import llm_backend
from app.banking.routing import SERVICE_DESCRIPTIONS
from app.config import settings
from experiments.dynamic_suite.doc_rows import parse
from experiments.dynamic_suite.expect import EXPECT, EXTRA_ROWS, key_of

CACHE = Path(__file__).with_name("questions.json")
MULTILINGUAL_CACHE = Path(__file__).with_name("questions_multilingual.json")
MULTILINGUAL_STYLES = {
    "bangla_short": "two to four words in Bangla script (বাংলা), the way people text",
    "bangla_sentence": "one complete, natural sentence in Bangla script (বাংলা)",
    "banglish_short": "two to four words of Banglish: Bangla written in English letters (e.g. \"balance koto\"), with casual spelling",
    "banglish_sentence": "one casual sentence of Banglish: Bangla written in English letters, the way people text, with an English banking word or two",
    "mixed": "one sentence that mixes Bangla script and English words, as bilingual customers often write (e.g. \"আমার card টা block করেন\")",
}
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


async def write_questions(want: str, styles_map: dict = STYLES) -> dict:
    styles = "\n".join(f'- "{k}": {v}' for k, v in styles_map.items())
    language = "(in English)" if styles_map is STYLES else "(in Bangla, Banglish or both)"
    prompt = (
        f"Customers of a Bangladeshi bank type messages {language} into the bank's chat assistant in the "
        "mobile app. Write five different messages from ONE customer who wants this:\n"
        f"{want}\n\nStyles, one message each:\n{styles}\n\n"
        "Each message must be something a real person would type, worded differently from the "
        "others, and must not use technical words such as API, endpoint or service. Use any "
        "details a real customer might mention (an amount, a bank or wallet name, a date) when "
        "they fit. Reply only with JSON whose keys are the five style names."
    )
    data = await llm_backend.post(
        "/api/chat",
        {"model": settings.OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}],
         "stream": False, "format": "json", "think": settings.OLLAMA_THINK,
         "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.8}},
        timeout=120,
    )
    got = json.loads(data["message"]["content"])
    return {k: str(got.get(k) or "").strip() for k in styles_map if str(got.get(k) or "").strip()}


async def main(regen: bool, only: set[str], multilingual: bool = False):
    cache_path, styles_map = (MULTILINGUAL_CACHE, MULTILINGUAL_STYLES) if multilingual else (CACHE, STYLES)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() and not regen else {}
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
        if key in cache and len(cache[key]["questions"]) == len(styles_map):
            continue
        for _ in range(3):
            questions = await write_questions(want_of(name, expected, extra), styles_map)
            if len(questions) == len(styles_map):
                break
        cache[key] = {"intent": intent, "name": name, "expected": list(expected) if isinstance(expected, tuple) else expected,
                      "questions": questions}
        print(f"{key:28} {questions}", flush=True)
        cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    print(f"{len(cache)} rows cached in {cache_path.name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else set()
    asyncio.run(main("--regen" in args, only, "--multilingual" in args))
