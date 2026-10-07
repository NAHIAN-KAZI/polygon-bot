# FALLBACK — Integration Handoff

Off-topic questions, abuse, gibberish, and general bank-product questions.
Read `COMMON.md` first.

The bank's own FAQ / "Polygon AI" hand-off endpoints are **not used** — the
chatbot answers product questions from the bank's knowledge-base documents
(uploaded via `POST /documents`, see `INTEGRATION.md`) and declines anything
unrelated to Polygon Bank.

## What the bot does for each request in this intent

The status doc lists the bank's 7 FALLBACK endpoints (Polygon AI chat/status, FAQ
categories, FAQs, submit complaint) as unused by design. The bot never calls them.

| Request | Outcome |
|---|---|
| Product/policy question | Handled in chat: `KB_ANSWER` from the uploaded knowledge base |
| Off-topic, maths | Handled in chat: `KB_ANSWER`, polite decline (`grounded: false`) |
| Abuse, gibberish, vague | `CLARIFICATION_REQUIRED` (may offer concrete options in the text) |
| A complaint | Executed in chat after yes/no (`support` / `submit_complaint`, see `CARD_ISSUE.md`) |
| A change the chat doesn't carry out | `APP_ACTION` (`COMMON.md` §8) |

## Behaviour

Bubble wording is model-written and varies; the examples show the gist.

| Customer says | `result.type` | Bubble |
|---|---|---|
| "what is a savings account" (product/policy) | `KB_ANSWER` | Answer from the uploaded documents; `payload.sources` lists them |
| "who is the prime minister of japan", "what is 12 * 12" | `KB_ANSWER` | "I'm only able to help with questions about your Polygon Bank account and Polygon Bank's services." |
| "you are the worst bot ever", "asdfgh" | `CLARIFICATION_REQUIRED` | Asks what they need, may list what it can help with (no engaging with abuse) |
| A change chat doesn't carry out (unfreeze, PIN reset, KYC…) | `APP_ACTION` | Says where in the app it's done; the app shows the action card |

## Response — `result.payload`

```json
{"type": "KB_ANSWER", "payload": {"grounded": true, "hitCount": 5,
  "sources": ["Polygon_Bank_Knowledge_Base.pdf"]}}
```
`grounded: false` / `sources: null` → the reply is a decline, not a document answer.

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| — | General bank knowledge and off-topic | Answered in chat | **U1 only** — Text answer or a polite decline; no sources, no payload. | None | None | — |

<!-- UI-TO-BUILD:END -->

## Frontend integration (Dart)

```dart
void renderFallback(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  if (turn.type == 'KB_ANSWER' && p['grounded'] == true) {
    showSourcesFooter((p['sources'] as List? ?? const []).cast<String>());
  }
}
```

Rendering: bubble only; for grounded answers an optional small "Source: …" line.
After two clarifying questions in a row you may offer "Talk to an agent" (the
app's own support screen). Count them by `result.type`, not by bubble text.

## Live-verified (2026-10-03)

- Off-topic and maths → polite decline (`KB_ANSWER`, ungrounded).
- Abuse and gibberish → "What exactly do you need help with?".
- "what is a savings account" → grounded answer from `Polygon_Bank_Knowledge_Base.pdf`.

## Known gaps

1. "what documents do i need to open an account" sometimes gets a clarifying question instead of a document answer.
2. Answer quality depends on what's uploaded to the knowledge base.
