# GREETING — Integration Handoff

Hello / salam / thanks. No bank API involved. Read `COMMON.md` first.

## What the bot does for each request in this intent

No status-doc rows and no bank API: greetings and thanks are handled in chat
(`CLARIFICATION_REQUIRED` or `KB_ANSWER`, below). Nothing is executed.

## Behaviour

| Customer says | `result.type` | Bubble (LLM-worded, varies) |
|---|---|---|
| "hi", "assalamualaikum, kemon achen", "help" | `CLARIFICATION_REQUIRED` | A greeting plus "what can I help you with?", sometimes listing what it can do |
| "thank you so much" | `KB_ANSWER` | "You're welcome. I'm here to help with any questions about your Polygon Bank account or our services." |

`payload` is `null` for `CLARIFICATION_REQUIRED`; for `KB_ANSWER` it is
`{"grounded": false, "hitCount": 0, "sources": null}`.

Replies are always in English (simple English when the customer writes Banglish).

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| — | Greeting and small talk | Answered in chat | **U1 only** — Text. The reply may offer what the bot can help with; no payload. | None | None | — |

<!-- UI-TO-BUILD:END -->

## Frontend integration (Dart)

Nothing to render beyond the bubble. A good place for quick-reply chips:

```dart
if (turn.type == 'CLARIFICATION_REQUIRED' && isFirstTurn) {
  showQuickReplies(['Balance', 'My cards', 'Recent transactions', 'Transfer money', 'Fees'],
      onTap: (label) => onSend(label));
}
```

The chips are plain messages — the bot understands them like typed text.

## Live-verified (2026-10-03)

- "hi", "assalamualaikum, kemon achen", "help" → "What can I help you with?" / "What exactly do you need help with?"
- "thank you so much" → polite closing (above).

## Known gaps

None specific. The app's own welcome message can be shown before the first turn
without calling the API.
