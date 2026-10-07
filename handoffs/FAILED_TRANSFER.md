# FAILED_TRANSFER — Integration Handoff

Money deducted but not received, a failed/wrong transaction, or a wrong
charge: the customer sees their transactions, existing disputes and tickets,
can raise a dispute (gathered in chat, **submitted in the app**), and can submit a
complaint (in chat, after a yes).
Read `COMMON.md` first.

## Services

| Ask | `category` / `service` | Status |
|---|---|---|
| Transaction history (8.1) | `polygon_services` / `transaction_history` | ✅ Live (see `MINI_STATEMENT.md`) |
| Raise dispute (8.2) | `service_requests` / `raise_dispute` | ✅ Gather + redirect (never POSTs) |
| List disputes (8.3) | `service_requests` / `disputes` | ✅ Live |
| Submit complaint (8.4) | `support` / `submit_complaint` | ✅ In chat after an explicit yes (approved change) |
| My complaints (8.5) | `polygon_services` / `my_tickets` | ✅ Live |

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 8.1 | Transaction history | Handled in chat: `polygon_services` / `transaction_history` |
| 8.2 | Raise dispute | Gather + redirect: `service_requests` / `raise_dispute`, `routing.action: "raise_dispute"` (never submitted by the bot) |
| 8.3 | List disputes | Handled in chat: `service_requests` / `disputes` |
| 8.4 | Submit complaint | Executed in chat after yes/no: `support` / `submit_complaint` (see `CARD_ISSUE.md` for the payload) |
| 8.5 | My complaints | Handled in chat: `polygon_services` / `my_tickets` |

## Raise dispute flow

The bot never asks the customer for what the bank already knows:

1. **Account**: one account → used; several → `ACCOUNT_SELECTION_REQUIRED` (bank-account
   entries; send `{"accountNumber": ...}`).
2. **Transaction**: the bot matches the customer's description against the 8 most recent
   transactions. No clear match → `TRANSACTION_SELECTION_REQUIRED` (`COMMON.md` §6); send
   `{"transactionId": ...}`.
3. **What went wrong** (`remarks`): asked in chat if missing (`CLARIFICATION_REQUIRED`).

Then it returns a summary and `routing.action: "raise_dispute"`:

| Field | Type | Meaning |
|---|---|---|
| `accountNumber` | string | The customer's account the transaction was on |
| `transactionReferenceNo` | string | Reference from the transaction / SMS |
| `remarks` | string | What went wrong, in the customer's words |
| `transactionSummary` | string | Present when the transaction was picked/matched: a short description of it |

Triggers (live): "I sent 3000 to my brother yesterday, money was deducted but he
never got it", "ATM took my card money but no cash came out",
"i want to raise a dispute".

## Response — `result`

**Gathering** → `ACCOUNT_SELECTION_REQUIRED` / `TRANSACTION_SELECTION_REQUIRED` /
`CLARIFICATION_REQUIRED` as above. If the bank lookup fails, the account and transaction are
not asked in chat: the summary arrives without `accountNumber` / `transactionReferenceNo`, and the
customer picks them on the app's dispute screen. Treat both as optional when prefilling.

**Summary** (live):
```json
{"type": "BANKING_SERVICE", "category": "service_requests", "service": "raise_dispute",
 "payload": {"accountNumber": "100126000056", "transactionReferenceNo": "TXN123456",
             "remarks": "3000 taka deducted but never reached my brother", "executed": false},
 "routing": {"category": "service_requests", "service": "raise_dispute", "action": "raise_dispute"}}
```

**Disputes / tickets**: `{"disputes": []}`, `{"complaints": []}`.

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 8.1 | Transaction history | Answered in chat | **U4** — Transaction list. | None | None | — |
| 8.2 | Raise dispute | Gather → inline box | Same as 2.2 | Submit dispute | Same as 2.2 | Same as 2.2 |
| 8.3 | List disputes | Answered in chat | **U2 disputes** — Same as 2.3. | None | None | — |
| 8.4 | Submit complaint | Executed in chat | Same as 3.5 | Yes / No (Send on the complaint box) | None | Same as 3.5 |
| 8.5 | My complaints | Answered in chat | **U2 tickets** — Same as 3.6. | None | None | — |

<!-- UI-TO-BUILD:END -->

## Frontend integration (Dart)

```dart
void renderFailedTransfer(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  if (turn.service == 'raise_dispute' && p['executed'] == false) {
    // U8 dispute box, prefilled. The box submits it (POST service-request/v1/disputes); the bot never does.
    showDisputeBox(prefill: {
      'accountNumber': p['accountNumber'],
      'transactionReferenceNo': p['transactionReferenceNo'],
      'remarks': p['remarks'],
    });
  }
}
```

The transaction picker comes from the backend (`TRANSACTION_SELECTION_REQUIRED`):
handle it with the shared case in `COMMON.md` §10 (amounts are poisha; send `"Selected"` +
`{"transactionId": ...}` with no `category`/`service`).

## Live-verified (2026-10-03, `taslim_islamic`)

- "I sent 3000 to my brother yesterday, money was deducted but he never got it" → `raise_dispute` gathering ("account number and transaction reference number?").
- "ATM took my card money but no cash came out" → same.
- Full details in one message → summary above, `executed: false`.
- "any open disputes", "status of my dispute" → `disputes`, "There are no open disputes."

## Known gaps

1. Banglish "taka kete nise kintu jay nai" ("money was deducted but didn't go") was read as a new transfer (2026-10-03); not re-checked since.
2. The transaction picker and account lookup were added after the 2026-10-03 live check; the
   2026-10-06 live run routed 4 of 5 dispute phrasings to `raise_dispute` (single turn, picker not exercised).
3. Complaint submission: 2026-10-06 live run, 1 of 5 phrasings reached the complaint flow in one turn; the rest got a clarifying question first.
