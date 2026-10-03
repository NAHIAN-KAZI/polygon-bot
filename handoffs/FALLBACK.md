# FALLBACK — Integration Handoff

Off-topic questions, abuse, gibberish, and general bank-product questions.
Read `COMMON.md` first.

The bank's own FAQ / "Polygon AI" hand-off endpoints are **not used** — the
chatbot answers product questions from the bank's knowledge-base documents
(uploaded via `POST /documents`, see `INTEGRATION.md`) and declines anything
unrelated to Polygon Bank.

## Behaviour

| Customer says | `result.type` | Bubble |
|---|---|---|
| "what is a savings account" (product/policy) | `KB_ANSWER` | Answer from the uploaded documents; `payload.sources` lists them |
| "who is the prime minister of japan", "what is 12 * 12" | `KB_ANSWER` | "I'm only able to help with questions about your Polygon Bank account and Polygon Bank's services." |
| "you are the worst bot ever", "asdfgh" | `CLARIFICATION_REQUIRED` | "What exactly do you need help with?" (no engaging with abuse) |
| A change chat can't make (unfreeze, PIN reset, change email…) | `CLARIFICATION_REQUIRED` | "…can only be done in the app. What else do you need?" |

## Response — `result.payload`

```json
{"type": "KB_ANSWER", "payload": {"grounded": true, "hitCount": 5,
  "sources": ["Polygon_Bank_Knowledge_Base.pdf"]}}
```
`grounded: false` / `sources: null` → the reply is a decline, not a document answer.

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
app's own support screen).

## Live-verified (2026-10-03)

- Off-topic and maths → polite decline (`KB_ANSWER`, ungrounded).
- Abuse and gibberish → "What exactly do you need help with?".
- "what is a savings account" → grounded answer from `Polygon_Bank_Knowledge_Base.pdf`.

## Known gaps

1. "what documents do i need to open an account" sometimes gets a clarifying question instead of a document answer.
2. Answer quality depends on what's uploaded to the knowledge base.
