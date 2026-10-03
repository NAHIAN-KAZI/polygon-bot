# ATM_SUPPORT — Integration Handoff

ATM problems (card charged, no cash), dispute status, and cash-by-code.
Read `COMMON.md` first; the dispute gathering is detailed in `FAILED_TRANSFER.md`.

## Services

| Ask | `category` / `service` | Status |
|---|---|---|
| Cash by code (2.1) | — | ⛔ Blocked — bot says it can only be done in the app |
| Raise dispute (2.2) | `service_requests` / `raise_dispute` | ✅ Gather + redirect (never submits) |
| List disputes (2.3) | `service_requests` / `disputes` (`GET service-request/v1/disputes`) | ✅ Live |

## How to trigger

Live-tested:
- "ATM took my card money but no cash came out" → `raise_dispute` gathering.
- "any open disputes", "status of my dispute" → `disputes`.
- "i want to withdraw cash by code" → "…can only do that in the app."

Direct route: `{"message": "show", "category": "service_requests", "service": "disputes"}`.

## Response — `result.payload`

**disputes** (live): `{"disputes": []}` — empty is the normal "none" answer.

**raise_dispute** summary: see `FAILED_TRANSFER.md` (`accountNumber`,
`transactionReferenceNo`, `remarks`, `executed: false`, `routing.action: "raise_dispute"`).

**cash by code**: `CLARIFICATION_REQUIRED`, bubble only.

## Frontend integration (Dart)

```dart
void renderAtmSupport(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'disputes':
      final items = (p['disputes'] as List);
      if (items.isNotEmpty) showDisputeList(items.cast<Map<String, dynamic>>());
    case 'raise_dispute':
      showDisputeSummaryCard(p, onContinue: () => openAppScreen('raise_dispute', prefill: p));
  }
}
```

Rendering: dispute list as status rows; a "Cash by code" shortcut, if wanted,
opens the app's own screen (the bubble already tells the customer to use the app).

## Live-verified (2026-10-03, `taslim_islamic`)

All three triggers above, with the results shown.

## Known gaps

1. Non-empty dispute entries not seen live — confirm fields before finalising rows.
