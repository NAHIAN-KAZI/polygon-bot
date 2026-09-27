"""Standalone experiment — NOT wired into the production app.

Same 14-intent classification test as test_14_intents_classification.py, but
with exactly 50 test messages (more phrasings per intent) for a larger sample.

Run directly on the host (needs network access to Ollama):
    python3 experiments/test_50_cases_classification.py
"""
from __future__ import annotations

import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1:8b"

INTENT_DESCRIPTIONS: dict[str, str] = {
    "ACCOUNT_INFO": "General questions about the customer's own account details (not a specific balance/statement request).",
    "ATM_SUPPORT": "Finding a nearby ATM, or an ATM malfunction (card retained, cash not dispensed, etc).",
    "CARD_ISSUE": "A generic problem with a card that isn't clearly a replacement or lost/stolen report (e.g. card declined, card not working).",
    "CARD_MANAGEMENT": "Managing card settings — limits, enabling/disabling features, activating a new card.",
    "CARD_REPLACEMENT": "Requesting a replacement card because the old one is damaged, expired, or worn out (not lost/stolen).",
    "CHECK_BALANCE": "Asking how much money is in an account.",
    "EDIT_PERSONAL_DETAILS": "Updating personal profile info — address, phone, email, name.",
    "FAILED_TRANSFER": "A transfer the customer already attempted did not go through, asking why or what to do.",
    "FALLBACK": "Message doesn't match any known banking intent — gibberish, unrelated, or unclear.",
    "FEES": "Asking about fees/charges for a banking service.",
    "GREETING": "A simple greeting with no actual request yet (hi, hello, good morning).",
    "LOST_OR_STOLEN_CARD": "Reporting a card as lost or stolen, needing it blocked urgently.",
    "MINI_STATEMENT": "Asking for a short list/summary of recent transactions.",
    "TRANSFER": "Wants to send money to someone or another account.",
}


def build_tool_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "classify_intent",
                "description": "Classify the customer's message into exactly one known banking intent.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "enum": list(INTENT_DESCRIPTIONS.keys()),
                            "description": "The single best-matching intent for this message.",
                        }
                    },
                    "required": ["intent"],
                },
            },
        }
    ]


def build_system_prompt() -> str:
    lines = ["You are a banking assistant's intent classifier. Given a customer message, "
             "call classify_intent with exactly one of these intents:\n"]
    for name, desc in INTENT_DESCRIPTIONS.items():
        lines.append(f"- {name}: {desc}")
    lines.append(
        "\nAlways call classify_intent. Never answer in plain text. Pick the single "
        "best match even if imperfect."
    )
    return "\n".join(lines)


def classify(message: str) -> str | None:
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": message},
        ],
        "tools": build_tool_schema(),
        "stream": False,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    tool_calls = data.get("message", {}).get("tool_calls") or []
    if not tool_calls:
        return None
    args = tool_calls[0]["function"].get("arguments", {})
    return args.get("intent")


# Exactly 50 test cases — 3 or 4 phrasings per intent.
TEST_CASES: list[tuple[str, str]] = [
    ("ACCOUNT_INFO", "can you tell me my account details"),
    ("ACCOUNT_INFO", "what type of account do I have"),
    ("ACCOUNT_INFO", "give me information about my account"),
    ("ATM_SUPPORT", "where is the nearest ATM"),
    ("ATM_SUPPORT", "the ATM ate my card"),
    ("ATM_SUPPORT", "is there an ATM near Gulshan"),
    ("ATM_SUPPORT", "the ATM didn't give me cash but deducted money"),
    ("CARD_ISSUE", "my card is not working"),
    ("CARD_ISSUE", "my card keeps getting declined"),
    ("CARD_ISSUE", "why is my card not accepted at this shop"),
    ("CARD_MANAGEMENT", "I want to manage my card settings"),
    ("CARD_MANAGEMENT", "can you increase my card's daily limit"),
    ("CARD_MANAGEMENT", "please enable international transactions on my card"),
    ("CARD_MANAGEMENT", "how do I activate my new card"),
    ("CARD_REPLACEMENT", "I lost my card, I need a new one"),
    ("CARD_REPLACEMENT", "my card is damaged, can I get a replacement"),
    ("CARD_REPLACEMENT", "my card expired, please issue a new one"),
    ("CHECK_BALANCE", "what is my account balance"),
    ("CHECK_BALANCE", "how much money do I have"),
    ("CHECK_BALANCE", "check my current balance please"),
    ("CHECK_BALANCE", "how much is left in my savings account"),
    ("EDIT_PERSONAL_DETAILS", "I want to update my address"),
    ("EDIT_PERSONAL_DETAILS", "can you change my phone number on file"),
    ("EDIT_PERSONAL_DETAILS", "I need to update my email address"),
    ("FAILED_TRANSFER", "my transfer failed, what happened"),
    ("FAILED_TRANSFER", "the money I sent yesterday never arrived"),
    ("FAILED_TRANSFER", "why did my payment not go through"),
    ("FAILED_TRANSFER", "my transaction shows failed status"),
    ("FALLBACK", "asdkjaslkdj random gibberish text"),
    ("FALLBACK", "what's the weather like today"),
    ("FALLBACK", "tell me a joke"),
    ("FEES", "what fees do you charge for transfers"),
    ("FEES", "how much does a card replacement cost"),
    ("FEES", "is there a monthly maintenance fee"),
    ("GREETING", "hi there"),
    ("GREETING", "good morning"),
    ("GREETING", "hello, how are you"),
    ("LOST_OR_STOLEN_CARD", "my card was stolen, please block it"),
    ("LOST_OR_STOLEN_CARD", "I think someone took my card, freeze it now"),
    ("LOST_OR_STOLEN_CARD", "I lost my wallet with my card in it, block it immediately"),
    ("LOST_OR_STOLEN_CARD", "someone stole my purse, my debit card was inside"),
    ("MINI_STATEMENT", "show me a mini statement"),
    ("MINI_STATEMENT", "can I see my last few transactions"),
    ("MINI_STATEMENT", "give me a quick summary of recent activity"),
    ("TRANSFER", "I want to transfer money"),
    ("TRANSFER", "send 500 taka to my friend"),
    ("TRANSFER", "can you help me send money to another account"),
    ("TRANSFER", "I need to move funds to my brother's account"),
    ("ACCOUNT_INFO", "what is my account number"),
    ("ATM_SUPPORT", "list ATMs close to my location"),
]

assert len(TEST_CASES) == 50, f"expected exactly 50 cases, got {len(TEST_CASES)}"


def main() -> None:
    correct = 0
    per_intent: dict[str, list[bool]] = {k: [] for k in INTENT_DESCRIPTIONS}
    rows: list[dict] = []

    print(f"{'expected':25s} {'got':25s} {'message'}")
    print("-" * 90)
    for expected, message in TEST_CASES:
        got = classify(message)
        ok = got == expected
        correct += ok
        per_intent[expected].append(ok)
        marker = "OK" if ok else "FAIL"
        print(f"{expected:25s} {str(got):25s} {message}  [{marker}]")
        rows.append({"expected": expected, "got": got, "message": message, "ok": ok})

    total = len(TEST_CASES)
    print("-" * 90)
    print(f"Overall: {correct}/{total} correct ({100 * correct / total:.0f}%)")
    print()
    print("Per-intent accuracy:")
    for intent, results in per_intent.items():
        n_ok = sum(results)
        n_total = len(results)
        print(f"  {intent:25s} {n_ok}/{n_total}")

    with open("/mnt/data/tmp/claude-1000/-mnt-data-github-chatbot/a82a9da2-c995-4aae-9db2-0df99b2b29d1/scratchpad/50cases_results.json", "w") as f:
        json.dump({"rows": rows, "correct": correct, "total": total}, f, indent=2)


if __name__ == "__main__":
    main()
