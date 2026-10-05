"""Try learn-abc/halsa-bankingdemo-multilingual-intent-classifier (MuRIL, 14 banking
intents, EN/BN/Banglish) on the same 74 labelled messages as our live sweep
(experiments/eval_sweep.py), plus a few Bangla-script and edge messages.

  cd experiments/hf_intent_classifier && .venv/bin/python run_test.py
"""
import os
import sys
import time
from collections import defaultdict

os.environ.setdefault("HF_HOME", os.path.join(os.path.dirname(__file__), ".hf_cache"))
os.environ.setdefault("EVAL_API_KEY", "unused")  # eval_sweep imports eval_conversation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from transformers import pipeline  # noqa: E402

from eval_sweep import CASES  # noqa: E402  (intent, style, message, accepted)

MODEL = "learn-abc/halsa-bankingdemo-multilingual-intent-classifier"

EXTRA = [  # Bangla script and other cases not in the sweep
    ("CHECK_BALANCE", "bangla", "আমার একাউন্টে কত টাকা আছে?"),
    ("TRANSFER", "bangla", "আমি বিকাশে ৫০০ টাকা পাঠাতে চাই"),
    ("LOST_OR_STOLEN_CARD", "bangla", "আমার কার্ড হারিয়ে গেছে"),
    ("FEES", "bangla", "অন্য ব্যাংকে টাকা পাঠালে চার্জ কত?"),
    ("MINI_STATEMENT", "bangla", "আমার শেষ কয়েকটা লেনদেন দেখাও"),
    ("FEES", "banglish", "mobile wallet e 500 pathale koto charge"),
    ("FEES", "english", "i want to know the fees of money transfering"),
    ("FAILED_TRANSFER", "banglish", "taka kete nise kintu jay nai"),
    ("ATM_SUPPORT", "english", "Atm took my card money but no cash money come out"),
]


def main():
    started = time.monotonic()
    clf = pipeline("text-classification", model=MODEL, device=-1)
    print(f"loaded in {time.monotonic() - started:.1f}s; labels: {sorted(clf.model.config.id2label.values())}\n")

    rows = [(i, s, m) for i, s, m, _ in CASES if i != "MIXED"] + EXTRA
    per_intent = defaultdict(lambda: [0, 0])
    timings = []
    for intent, style, message in rows:
        t0 = time.monotonic()
        out = clf(message)[0]
        timings.append(time.monotonic() - t0)
        hit = out["label"] == intent
        per_intent[intent][0] += hit
        per_intent[intent][1] += 1
        flag = "OK " if hit else "BAD"
        print(f"{flag} [{intent}/{style}] {message[:70]!r} -> {out['label']} ({out['score']:.2f})")

    total = sum(v[1] for v in per_intent.values())
    good = sum(v[0] for v in per_intent.values())
    print(f"\n{good}/{total} correct  |  avg {1000 * sum(timings) / len(timings):.0f} ms/message on CPU")
    for intent, (g, n) in sorted(per_intent.items()):
        print(f"  {intent:22} {g}/{n}")


if __name__ == "__main__":
    main()
