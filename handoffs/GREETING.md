# GREETING — Integration Handoff

Hello / salam / thanks. No bank API involved. Read `COMMON.md` first.

## Behaviour

| Customer says | `result.type` | Bubble (LLM-worded, varies) |
|---|---|---|
| "hi", "assalamualaikum, kemon achen", "help" | `CLARIFICATION_REQUIRED` | "What can I help you with?" |
| "thank you so much" | `KB_ANSWER` | "You're welcome. I'm here to help with any questions about your Polygon Bank account or our services." |

`payload` is `null` for `CLARIFICATION_REQUIRED`; for `KB_ANSWER` it is
`{"grounded": false, "hitCount": 0, "sources": null}`.

Replies are always in English (simple English when the customer writes Banglish).

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
