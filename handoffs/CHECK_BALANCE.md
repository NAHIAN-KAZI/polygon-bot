# CHECK_BALANCE — Integration Handoff

Account balance and credit-card summary (limit, due, available credit).
Read `COMMON.md` first.

## Services

| Ask | `category` / `service` | Bank endpoint | Status |
|---|---|---|---|
| Account balance (6.1) | `account_info` / `balance` | `GET transfer/v1/accounting/balance` | ✅ Live |
| Credit card summary (6.2) | `card_info` / `credit_card_summary` | `GET card/v1/cards/{id}/credit-summary` | ✅ Live ("no credit card" verified) |

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 6.1 | Account balance | Handled in chat: `account_info` / `balance` (several accounts → `ACCOUNT_SELECTION_REQUIRED`) |
| 6.2 | Credit card summary | Handled in chat: `card_info` / `credit_card_summary` (several credit cards → selection, card shape) |

Nothing in this intent changes data.

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 6.1 | Account balance | Answered in chat | **U3 balance** — Balance prominent, account ending below; U5 first if several accounts. | None | None | — |
| 6.2 | Credit card summary | Answered in chat | **U3 credit card** — Limit, outstanding or due amount, available credit. No credit card → bubble only. | None | None | — |

<!-- UI-TO-BUILD:END -->

## How to trigger

Live-tested: "balance", "blance", "amar account e koto taka ase",
"WHY CANT I SEE MY MONEY. how much do i even have left???", "credit card limit left?".

Direct route: `{"message": "show", "category": "account_info", "service": "balance"}`.

## Request payload

| Service | Field | Required | Notes |
|---|---|---|---|
| `balance` | `accountNumber` | — | Auto-picked with one account; several → `ACCOUNT_SELECTION_REQUIRED` |
| `credit_card_summary` | `cardId` | — | Auto-picked with one credit card; several → selection (cards shape) |

## Response — `result.payload`

**balance** (live):
```json
{"balance": 9000000, "balanceFormatted": "৳90,000.00"}
```
`balance` is poisha; `balanceFormatted` is ready to show.

**credit_card_summary**, customer **without** a credit card (live) — a normal
answer, not an error:
```json
{"creditCard": null, "answer": "You don't have a credit card with Polygon Bank."}
```

**credit_card_summary**, customer with a credit card — the bank's summary,
wrapped as `{"creditSummary": {...}}`; money fields in poisha (limit,
outstanding, minimum due, available). Shape not yet observed live (see gaps).

## Frontend integration (Dart)

```dart
void renderBalance(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'balance':
      showBalanceCard(
        amount: p['balanceFormatted'] ?? Money.fromPoisha(p['balance']).format(),
      );
    case 'credit_card_summary':
      if (p['creditCard'] == null && p.containsKey('answer')) {
        return; // bubble already says they have no credit card
      }
      showCreditSummary((p['creditSummary'] as Map).cast<String, dynamic>());
  }
}
```

Rendering: a single balance card (one number, big). Credit summary as a small
card (limit / used / due / due date). Action button: optional "Open account"
(`routing.action` is `redirect`).

## Live-verified (2026-10-03, `taslim_islamic`)

- "balance", "blance", Banglish, all-caps angry → `balance`, "Tk 90,000.00".
- "credit card limit left?" → `credit_card_summary`, "You don't have a credit card with Polygon Bank…".

## Known gaps

1. A real credit-card summary payload hasn't been seen live (the dev user has no credit card) — confirm field names before building that card.
2. Multi-account selection unit-tested only.
