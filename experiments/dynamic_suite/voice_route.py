"""Voice routing check: the same status-doc questions, spoken. Each question is turned into
speech (edge-tts neural voices: Bangla bn-BD, English en-IN), transcribed by the app's own
transcriber (app.conversation.speech) and routed by classify() alone -- no bank, no replies.
It measures whether a spoken request reaches the right service, and how close the
transcript is to what was said.

  python -m experiments.dynamic_suite.voice_route [--only 1.6,4.8] [--styles bangla_sentence,mixed] [--stt nemo]

--stt nemo transcribes with the speech-to-text server (STT_URL, Titu STT) instead of the model.

Spoken styles: bangla_sentence and mixed (questions_multilingual.json), sentence (questions.json).
Banglish is not spoken: people who type Banglish speak Bangla.
Audio is cached in experiments/results/voice/; report in experiments/results/dynamic/voice_<time>.jsonl.
Needs `pip install edge-tts` and ffmpeg; sends the test sentences (no customer data) to the TTS service.
"""
import asyncio
import base64
import difflib
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import app.banking.taxonomy as taxonomy_module
from app.banking import ui_actions
from app.banking.routing import classify
from app.conversation.speech import AudioInputError, transcribe, transcribe_nemo
from experiments.dynamic_suite.checks import judge
from experiments.dynamic_suite.route_only import SNAPSHOT, as_result

HERE = Path(__file__).parent
RESULTS = Path(__file__).resolve().parents[1] / "results"
AUDIO = RESULTS / "voice"
SOURCES = [  # (questions file, style, voice)
    (HERE / "questions_multilingual.json", "bangla_sentence", "bn-BD-NabanitaNeural"),
    (HERE / "questions_multilingual.json", "mixed", "bn-BD-PradeepNeural"),
    (HERE / "questions.json", "sentence", "en-IN-NeerjaNeural"),
]


def speak(text: str, voice: str) -> str:
    """A data:audio/wav URL of `text` spoken by `voice` (16 kHz mono), cached on disk."""
    AUDIO.mkdir(parents=True, exist_ok=True)
    stem = AUDIO / hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16]
    wav = stem.with_suffix(".wav")
    if not wav.exists():
        mp3 = stem.with_suffix(".mp3")
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, "--text", text,
                        "--write-media", str(mp3)], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-ar", "16000", "-ac", "1", str(wav)],
                       check=True)
    return "data:audio/wav;base64," + base64.b64encode(wav.read_bytes()).decode()


def similarity(a: str, b: str) -> float:
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


async def main():
    arg = lambda name: set(sys.argv[sys.argv.index(name) + 1].split(",")) if name in sys.argv else set()
    only, styles = arg("--only"), arg("--styles")
    stt = "nemo" if "nemo" in arg("--stt") else "model"
    hear = transcribe_nemo if stt == "nemo" else transcribe
    cached = json.loads(SNAPSHOT.read_text())
    if not any(c["id"] == ui_actions.CATEGORY for c in cached["categories"]):
        cached["categories"].append(ui_actions.catalog_category())
    taxonomy_module._cache = cached
    taxonomy_module._index = taxonomy_module._build_index(cached["categories"])
    (RESULTS / "dynamic").mkdir(parents=True, exist_ok=True)
    records = []
    with open(RESULTS / "dynamic" / f"voice_{stt}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl", "w") as log:
        for path, style, voice in SOURCES:
            if styles and style not in styles:
                continue
            for key, row in json.loads(path.read_text()).items():
                if only and key not in only:
                    continue
                question = row["questions"].get(style)
                if not question:
                    continue
                expected = tuple(row["expected"]) if isinstance(row["expected"], list) else row["expected"]
                started = time.perf_counter()
                try:
                    heard = await hear(speak(question, voice))
                except AudioInputError as exc:
                    heard = ""
                    result = {"type": "TRANSPORT_ERROR", "error": str(exc)}
                heard_seconds = round(time.perf_counter() - started, 2)
                if heard:
                    result = as_result(await classify(heard, []))
                status, why = judge(expected, "", result)
                rec = {"row": key, "name": row["name"], "style": style, "voice": voice, "question": question,
                       "stt": stt, "heard": heard, "heard_seconds": heard_seconds,
                       "heard_similarity": round(similarity(question, heard), 2),
                       "got": f'{result.get("type")} {result.get("category")}/{result.get("service")}/{result.get("subservice")}',
                       "status": status, "why": why}
                records.append(rec)
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()
                if status != "PASS":
                    print(f"{status:8} {key:8} {style:15} {question[:40]!r} heard {heard[:40]!r} -> {rec['got']}", flush=True)
    print(f"\n{len(records)} spoken questions: {dict(Counter(r['status'] for r in records))}")
    for style in dict.fromkeys(r["style"] for r in records):
        rs = [r for r in records if r["style"] == style]
        sim = sum(r["heard_similarity"] for r in rs) / len(rs)
        secs = sum(r["heard_seconds"] for r in rs) / len(rs)
        print(f"  {style:16} {dict(Counter(r['status'] for r in rs))}  transcript similarity {sim:.2f}"
              f"  transcription {secs:.2f}s avg")


if __name__ == "__main__":
    asyncio.run(main())
