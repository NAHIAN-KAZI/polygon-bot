# CARD_ISSUE — Integration Handoff

A card problem: viewing complaints/tickets and disputes, raising a dispute
(gathered in chat, submitted in the app), and steering vague problems.
Read `COMMON.md` first; raising a dispute is detailed in `FAILED_TRANSFER.md`.

## Services

| Ask | `category` / `service` | Status |
|---|---|---|
| My complaints / tickets (3.6) | `polygon_services` / `my_tickets` (`GET support/v1/complaints`) | ✅ Live |
| List disputes (3.4) | `service_requests` / `disputes` | ✅ Live |
| Raise dispute (3.3) | `service_requests` / `raise_dispute` | ✅ Gather + redirect (never submits) |
| Unfreeze (3.2), reset PIN (3.1), submit complaint (3.5) | — | ⛔ Blocked — bot says "only in the app" |

"My Tickets" in the app = `GET support/v1/complaints` (confirmed by the bank
team); there is no separate ticket API.

## How the bot handles card problems

- "my card isnt working" → a question about what's happening (never a freeze).
- Lost/stolen/misused → freeze flow (`LOST_OR_STOLEN_CARD.md`).
- "show my complaints", "any update on my tickets?" → `my_tickets`.
- "status of my dispute", "any open disputes" → `disputes`.
- A charge/transaction problem → `raise_dispute` gathering.

## Response — `result.payload` (live)

**my_tickets**: `{"complaints": []}` · **disputes**: `{"disputes": []}`.
Empty = none (normal answer).

## Frontend integration (Dart)

```dart
void renderCardIssue(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'my_tickets':
      final items = (p['complaints'] as List);
      if (items.isNotEmpty) showTicketList(items.cast<Map<String, dynamic>>());
    case 'disputes':
      final items = (p['disputes'] as List);
      if (items.isNotEmpty) showDisputeList(items.cast<Map<String, dynamic>>());
    case 'raise_dispute':
      showDisputeSummary(p, onContinue: () => openAppScreen('raise_dispute', prefill: p));
  }
}
```

Rendering: tickets and disputes as status rows (reference, date, status chip);
"New complaint" opens the app's own complaint screen.

## Live-verified (2026-10-03, `taslim_islamic`)

- "show my complaints", "any update on my tickets?" → `my_tickets`, "no complaints".
- "unfreeze my card" → "You want to make your card usable again, but this can only be done in the app."
- "reset my card pin" → "…this can only be done in the app."
- "my card isnt working" → clarifying question, no service called.

## Known gaps

1. Non-empty complaint/dispute entries not seen live — confirm fields before finalising rows.
2. The wording of the "card isn't working" question varies run to run (LLM-worded); occasionally it adds advice that isn't in the facts.
