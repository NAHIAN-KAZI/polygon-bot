"""Standalone experiment — NOT wired into the production app.

Goal: measure whether llama3.1:8b (the model this repo uses for banking-service
classification, app/banking/routing.py) can reliably classify a message into
one of 14 intent labels the user supplied, which do NOT correspond to this
repo's real bank taxonomy (app/banking/taxonomy.py) — they're a separate,
hypothetical intent set.

This defines a dedicated tool schema + system prompt (independent of
build_tools()/build_system_prompt() in app/banking/routing.py) and 14 tiny
"demo adapters" that return canned mock data per intent, purely to prove the
classify -> adapter wiring end to end for each intent, the same shape as this
repo's real adapters (see app/banking/adapters/real.py) but with fake data.

Run directly on the host (needs network access to Ollama):
    python3 experiments/test_14_intents_classification.py
"""
from __future__ import annotations

import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1:8b"

# --- 14 demo "adapters" -----------------------------------------------------
# Each just returns canned mock data, mirroring app/banking/adapters/mock.py's
# MockAdapter shape ({"mock": True, ...}) — not real banking data.

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

DEMO_DATA: dict[str, dict] = {
    "ACCOUNT_INFO": {"mock": True, "intent": "ACCOUNT_INFO", "accountType": "Savings", "accountNumber": "XXXX1234", "status": "ACTIVE"},
    "ATM_SUPPORT": {"mock": True, "intent": "ATM_SUPPORT", "nearestAtm": "Banani Branch ATM, 0.4km away", "status": "operational"},
    "CARD_ISSUE": {"mock": True, "intent": "CARD_ISSUE", "cardStatus": "ACTIVE", "lastDeclineReason": "insufficient funds"},
    "CARD_MANAGEMENT": {"mock": True, "intent": "CARD_MANAGEMENT", "dailyLimit": 50000, "internationalUsage": False},
    "CARD_REPLACEMENT": {"mock": True, "intent": "CARD_REPLACEMENT", "eta": "5-7 business days", "fee": 200},
    "CHECK_BALANCE": {"mock": True, "intent": "CHECK_BALANCE", "balance": 125000.50, "currency": "BDT"},
    "EDIT_PERSONAL_DETAILS": {"mock": True, "intent": "EDIT_PERSONAL_DETAILS", "updatable_fields": ["address", "phone", "email"]},
    "FAILED_TRANSFER": {"mock": True, "intent": "FAILED_TRANSFER", "lastTransferStatus": "FAILED", "reason": "insufficient balance"},
    "FALLBACK": {"mock": True, "intent": "FALLBACK", "message": "I'm not sure I understood that."},
    "FEES": {"mock": True, "intent": "FEES", "transferFee": "0.5% (min 10 BDT)", "cardReplacementFee": 200},
    "GREETING": {"mock": True, "intent": "GREETING", "message": "Hello! How can I help you today?"},
    "LOST_OR_STOLEN_CARD": {"mock": True, "intent": "LOST_OR_STOLEN_CARD", "cardStatus": "BLOCKED", "blockedAt": "just now"},
    "MINI_STATEMENT": {"mock": True, "intent": "MINI_STATEMENT", "transactions": [{"amount": -500, "desc": "Grocery"}, {"amount": 2000, "desc": "Salary"}]},
    "TRANSFER": {"mock": True, "intent": "TRANSFER", "supportedChannels": ["own_account", "other_bank", "wallet"]},
}


def demo_adapter(intent: str) -> dict:
    """Stand-in for a real adapter's `fulfill()` — returns canned demo data."""
    return DEMO_DATA[intent]


# --- Classification tool schema (independent of app/banking/routing.py) ----

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


# --- Test cases: 2 paraphrasings per intent, to reduce single-sample noise --

TEST_CASES: list[tuple[str, str]] = [
    ("ACCOUNT_INFO", "can you tell me my account details"),
    ("ACCOUNT_INFO", "what type of account do I have"),
    ("ATM_SUPPORT", "where is the nearest ATM"),
    ("ATM_SUPPORT", "the ATM ate my card"),
    ("CARD_ISSUE", "my card is not working"),
    ("CARD_ISSUE", "my card keeps getting declined"),
    ("CARD_MANAGEMENT", "I want to manage my card settings"),
    ("CARD_MANAGEMENT", "can you increase my card's daily limit"),
    ("CARD_REPLACEMENT", "I lost my card, I need a new one"),
    ("CARD_REPLACEMENT", "my card is damaged, can I get a replacement"),
    ("CHECK_BALANCE", "what is my account balance"),
    ("CHECK_BALANCE", "how much money do I have"),
    ("EDIT_PERSONAL_DETAILS", "I want to update my address"),
    ("EDIT_PERSONAL_DETAILS", "can you change my phone number on file"),
    ("FAILED_TRANSFER", "my transfer failed, what happened"),
    ("FAILED_TRANSFER", "the money I sent yesterday never arrived"),
    ("FALLBACK", "asdkjaslkdj random gibberish text"),
    ("FALLBACK", "what's the weather like today"),
    ("FEES", "what fees do you charge for transfers"),
    ("FEES", "how much does a card replacement cost"),
    ("GREETING", "hi there"),
    ("GREETING", "good morning"),
    ("LOST_OR_STOLEN_CARD", "my card was stolen, please block it"),
    ("LOST_OR_STOLEN_CARD", "I think someone took my card, freeze it now"),
    ("MINI_STATEMENT", "show me a mini statement"),
    ("MINI_STATEMENT", "can I see my last few transactions"),
    ("TRANSFER", "I want to transfer money"),
    ("TRANSFER", "send 500 taka to my friend"),
]


def main() -> None:
    correct = 0
    per_intent: dict[str, list[bool]] = {k: [] for k in INTENT_DESCRIPTIONS}

    print(f"{'expected':25s} {'got':25s} {'message'}")
    print("-" * 90)
    for expected, message in TEST_CASES:
        got = classify(message)
        ok = got == expected
        correct += ok
        per_intent[expected].append(ok)
        marker = "OK" if ok else "FAIL"
        print(f"{expected:25s} {str(got):25s} {message}  [{marker}]")

        if ok:
            demo_result = demo_adapter(got)
            print(f"    -> demo adapter returned: {demo_result}")

    total = len(TEST_CASES)
    print("-" * 90)
    print(f"Overall: {correct}/{total} correct ({100 * correct / total:.0f}%)")
    print()
    print("Per-intent accuracy:")
    for intent, results in per_intent.items():
        n_ok = sum(results)
        n_total = len(results)
        print(f"  {intent:25s} {n_ok}/{n_total}")


if __name__ == "__main__":
    main()
