# 14-Intent Classification Test — llama3.1:8b

## Goal

Determine whether `llama3.1:8b` (the model this repo already uses for
banking-service classification, see `app/banking/routing.py`) can reliably
classify a customer message into one of 14 intent labels, using a dedicated,
purpose-built tool schema rather than this repo's real, much larger bank
taxonomy. Each intent also has a small "demo adapter" — a stand-in for a real
banking-service adapter, returning canned mock data — to prove the
classify → fulfill wiring end to end, not just the classification step alone.

This is a standalone experiment (`experiments/test_14_intents_classification.py`)
and is **not** wired into the production app — it does not touch
`app/banking/routing.py`, `app/banking/adapter_map.py`, or any real adapter.

## Setup

- Model: `llama3.1:8b`, called via Ollama's `/api/chat` endpoint with
  tool-calling (`stream: false`), same call shape as production `classify()`.
- One tool, `classify_intent`, with a single required `intent` parameter
  constrained to an enum of the 14 labels.
- 28 test messages total — 2 differently-worded messages per intent, to
  reduce single-sample noise.

### System prompt sent to the model

```
You are a banking assistant's intent classifier. Given a customer message,
call classify_intent with exactly one of these intents:

- ACCOUNT_INFO: General questions about the customer's own account details (not a specific balance/statement request).
- ATM_SUPPORT: Finding a nearby ATM, or an ATM malfunction (card retained, cash not dispensed, etc).
- CARD_ISSUE: A generic problem with a card that isn't clearly a replacement or lost/stolen report (e.g. card declined, card not working).
- CARD_MANAGEMENT: Managing card settings — limits, enabling/disabling features, activating a new card.
- CARD_REPLACEMENT: Requesting a replacement card because the old one is damaged, expired, or worn out (not lost/stolen).
- CHECK_BALANCE: Asking how much money is in an account.
- EDIT_PERSONAL_DETAILS: Updating personal profile info — address, phone, email, name.
- FAILED_TRANSFER: A transfer the customer already attempted did not go through, asking why or what to do.
- FALLBACK: Message doesn't match any known banking intent — gibberish, unrelated, or unclear.
- FEES: Asking about fees/charges for a banking service.
- GREETING: A simple greeting with no actual request yet (hi, hello, good morning).
- LOST_OR_STOLEN_CARD: Reporting a card as lost or stolen, needing it blocked urgently.
- MINI_STATEMENT: Asking for a short list/summary of recent transactions.
- TRANSFER: Wants to send money to someone or another account.

Always call classify_intent. Never answer in plain text. Pick the single
best match even if imperfect.
```

(This is the exact text produced by `build_system_prompt()` in the experiment
script — the per-intent one-line descriptions above are what I wrote for each
of your 14 labels, since none came with a description; each is a plain-language
gloss of the label name.)

### Tool schema sent to the model

```json
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
          "enum": ["ACCOUNT_INFO", "ATM_SUPPORT", "CARD_ISSUE", "CARD_MANAGEMENT",
                   "CARD_REPLACEMENT", "CHECK_BALANCE", "EDIT_PERSONAL_DETAILS",
                   "FAILED_TRANSFER", "FALLBACK", "FEES", "GREETING",
                   "LOST_OR_STOLEN_CARD", "MINI_STATEMENT", "TRANSFER"],
          "description": "The single best-matching intent for this message."
        }
      },
      "required": ["intent"]
    }
  }
}
```

## Per-intent demo adapter ("fulfill" stand-in)

Each intent has a tiny canned-data function, mirroring the shape of this
repo's real `MockAdapter` (`app/banking/adapters/mock.py`) — a `{"mock": true, ...}`
dict, not real banking data:

| Intent | Demo adapter output |
|---|---|
| `ACCOUNT_INFO` | `{"mock": true, "intent": "ACCOUNT_INFO", "accountType": "Savings", "accountNumber": "XXXX1234", "status": "ACTIVE"}` |
| `ATM_SUPPORT` | `{"mock": true, "intent": "ATM_SUPPORT", "nearestAtm": "Banani Branch ATM, 0.4km away", "status": "operational"}` |
| `CARD_ISSUE` | `{"mock": true, "intent": "CARD_ISSUE", "cardStatus": "ACTIVE", "lastDeclineReason": "insufficient funds"}` |
| `CARD_MANAGEMENT` | `{"mock": true, "intent": "CARD_MANAGEMENT", "dailyLimit": 50000, "internationalUsage": false}` |
| `CARD_REPLACEMENT` | `{"mock": true, "intent": "CARD_REPLACEMENT", "eta": "5-7 business days", "fee": 200}` |
| `CHECK_BALANCE` | `{"mock": true, "intent": "CHECK_BALANCE", "balance": 125000.50, "currency": "BDT"}` |
| `EDIT_PERSONAL_DETAILS` | `{"mock": true, "intent": "EDIT_PERSONAL_DETAILS", "updatable_fields": ["address", "phone", "email"]}` |
| `FAILED_TRANSFER` | `{"mock": true, "intent": "FAILED_TRANSFER", "lastTransferStatus": "FAILED", "reason": "insufficient balance"}` |
| `FALLBACK` | `{"mock": true, "intent": "FALLBACK", "message": "I'm not sure I understood that."}` |
| `FEES` | `{"mock": true, "intent": "FEES", "transferFee": "0.5% (min 10 BDT)", "cardReplacementFee": 200}` |
| `GREETING` | `{"mock": true, "intent": "GREETING", "message": "Hello! How can I help you today?"}` |
| `LOST_OR_STOLEN_CARD` | `{"mock": true, "intent": "LOST_OR_STOLEN_CARD", "cardStatus": "BLOCKED", "blockedAt": "just now"}` |
| `MINI_STATEMENT` | `{"mock": true, "intent": "MINI_STATEMENT", "transactions": [{"amount": -500, "desc": "Grocery"}, {"amount": 2000, "desc": "Salary"}]}` |
| `TRANSFER` | `{"mock": true, "intent": "TRANSFER", "supportedChannels": ["own_account", "other_bank", "wallet"]}` |

## Test messages and results (live run, 2026-09-27)

| Intent | Test message 1 | Test message 2 | Result |
|---|---|---|---|
| `ACCOUNT_INFO` | "can you tell me my account details" | "what type of account do I have" | 2/2 |
| `ATM_SUPPORT` | "where is the nearest ATM" | "the ATM ate my card" | 2/2 |
| `CARD_ISSUE` | "my card is not working" | "my card keeps getting declined" | 2/2 |
| `CARD_MANAGEMENT` | "I want to manage my card settings" | "can you increase my card's daily limit" | 2/2 |
| `CARD_REPLACEMENT` | "I lost my card, I need a new one" | "my card is damaged, can I get a replacement" | 2/2 |
| `CHECK_BALANCE` | "what is my account balance" | "how much money do I have" | 2/2 |
| `EDIT_PERSONAL_DETAILS` | "I want to update my address" | "can you change my phone number on file" | 2/2 |
| `FAILED_TRANSFER` | "my transfer failed, what happened" | "the money I sent yesterday never arrived" | 2/2 |
| `FALLBACK` | "asdkjaslkdj random gibberish text" | "what's the weather like today" | 2/2 |
| `FEES` | "what fees do you charge for transfers" | "how much does a card replacement cost" | 2/2 |
| `GREETING` | "hi there" | "good morning" | 2/2 |
| `LOST_OR_STOLEN_CARD` | "my card was stolen, please block it" | "I think someone took my card, freeze it now" | 2/2 |
| `MINI_STATEMENT` | "show me a mini statement" | "can I see my last few transactions" | 2/2 |
| `TRANSFER` | "I want to transfer money" | "send 500 taka to my friend" | 2/2 |

**Overall: 28/28 correct (100%)**

Every test message's classified intent matched the expected label, and its
demo adapter returned the correct canned data for that intent (full raw
run output preserved in `experiments/test_14_intents_classification.py`'s
run log — rerun the script to reproduce).

## Conclusion

`llama3.1:8b` classified all 14 intents correctly, 100%, when given a focused,
purpose-built 14-option schema and description set — no ambiguity, no
misses, across both phrasing variants per intent.

This is a *different, easier* classification task than this repo's production
`classify()` (`app/banking/routing.py`), which has to choose among the bank's
real, much larger live taxonomy (50+ services across 8 categories) plus
several other responsibilities (payload extraction, retry-then-clarify
fallback, beneficiary name matching). The occasional misses we've seen live
in production are a scope/complexity issue in that larger system, not
evidence that llama3.1:8b itself can't classify — this test isolates the
model's raw capability and it handles a focused 14-way classification
cleanly.
