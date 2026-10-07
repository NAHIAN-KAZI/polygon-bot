# MINI_STATEMENT — Integration Handoff

Recent transactions / statement, for an account or a credit card.
Read `COMMON.md` first.

## Services

| Ask | `category` / `service` | Bank endpoint | Status |
|---|---|---|---|
| Transaction list (13.1) | `polygon_services` / `transaction_history` | `GET transfer/v1/accounting/transaction-list` | ✅ Live |
| Account transactions (13.2) | `account_info` / `account_transactions` | `GET polygon-bank/v1/accounts/{id}/transactions` | ✅ Live (direct route; chat uses 13.1) |
| Credit card statement (13.3) | `card_info` / `credit_card_statement` | `GET card/v1/cards/{id}/statements` | ✅ Live ("no credit card" verified) |
| Expense tracker by category (13.4) | — | — | ❌ Not built |

Any transactions/statement/spending ask goes to `transaction_history`; the bot
then checks which account (asks if several).

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 13.1 | Transaction list | Handled in chat: `polygon_services` / `transaction_history` (several accounts → `ACCOUNT_SELECTION_REQUIRED`) |
| 13.2 | Account transactions | Handled in chat (the bot uses 13.1 for chat asks) |
| 13.3 | Credit card statement | Handled in chat: `card_info` / `credit_card_statement` |
| 13.4 | Expense tracker by category | Not built: the bot does not offer it (no backend) |

Nothing in this intent changes data.

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 13.1 | Transaction list | Answered in chat | **U4** — Transaction list (U5 first if several accounts). | None | None | — |
| 13.2 | Account transactions | Answered in chat | **U4** — Same as 13.1. | None | None | — |
| 13.3 | Credit card statement | Answered in chat | **U3/U2 statement** — Billed or unbilled statement with its transactions. | None | None | — |

<!-- UI-TO-BUILD:END -->

## How to trigger

Live-tested: "statement", "trnsactions", "Hello team, … Please show my latest
transactions." (multi-line), "credit card statement this month",
"whats my balance and also show my last transactions".

Direct route: `{"message": "show", "category": "polygon_services", "service": "transaction_history", "payload": {"startDate": "2026-09-01", "endDate": "2026-09-30"}}`.

## Request payload

| Service | Field | Required | Notes |
|---|---|---|---|
| `transaction_history` | `accountNumber` | — | Auto-picked with one account; several → selection |
| `transaction_history` | `startDate`, `endDate` | — | `yyyy-MM-dd`; adds `dateFiltered: true` to the result |
| `transaction_history` | `page`, `size` | — | Default 0 / 10 |
| `credit_card_statement` | `cardId` | — | Auto-picked with one credit card |
| `credit_card_statement` | `month` | — | `yyyy-MM`, default current month |
| `credit_card_statement` | `isBilled` | — | Default `false` (unbilled, current activity) |

## Response — `result.payload`

**transaction_history** (live, trimmed; `amount` and `balance` in poisha;
`balance` on a row is the balance **after that transaction**, not the
current balance):
```json
{"transactions": [{"id": 5354, "txnTime": "2026-09-29T10:05:20Z", "type": "DEBIT",
   "amount": 500000, "balance": 9000000, "transactionType": "bKash",
   "description": "bKash: From 100126000056 to 10002030",
   "accountNumber": "100126000056", "accountNumberMasked": "••••••••0056",
   "amountFormatted": "৳5,000.00", "icon": "https://…/icons/….png",
   "isRefunded": false, "transactionId": "20260929160519764-…"}],
 "pagination": {"totalCount": 3, "currentPage": 0, "hasNext": false}}
```

**credit_card_statement**, no credit card (live):
`{"creditCard": null, "answer": "You don't have a credit card with Polygon Bank."}`.
With a card: `{"statements": [...]}` (bank shape, poisha).

## Frontend integration (Dart)

```dart
void renderStatement(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  if (turn.service == 'transaction_history') {
    final txns = (p['transactions'] as List).cast<Map<String, dynamic>>();
    showTransactionTable([
      for (final t in txns)
        TxnRow(
          when: DateTime.parse(t['txnTime']).toLocal(),
          title: t['transactionType'],
          debit: t['type'] == 'DEBIT',
          amount: t['amountFormatted'] ?? Money.fromPoisha(t['amount']).format(),
          icon: t['icon'],
        )
    ], hasMore: p['pagination']?['hasNext'] == true);
  } else if (turn.service == 'credit_card_statement' && p['creditCard'] != null) {
    showStatement((p['statements'] as List).cast<Map<String, dynamic>>());
  }
}
```

Rendering: a compact table/list (date, type icon, title, ± amount) — many rows,
same columns. "View more" can resend with `payload: {'page': n + 1}` and the
same direct route. Don't show a row's `balance` as the account balance.

## Live-verified (2026-10-03, `taslim_islamic`)

- "statement", "trnsactions", multi-line reconcile message → 3 real transactions.
- "whats my balance and also show my last transactions" → "current balance is Tk 90,000.00" + latest transactions (fixed: it used to quote a row's running balance).
- "credit card statement this month" → "You don't have a credit card…".

## Known gaps

1. "last koyta lenden dekhao" (Banglish) still gets a "what do you want to see?" question instead of the list.
2. Expense tracker (13.4) not built (needs a category list from an endpoint outside the supplied 46).
3. Real credit-card statement shape not seen live.
