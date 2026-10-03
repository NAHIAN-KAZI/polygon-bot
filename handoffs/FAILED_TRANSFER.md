# FAILED_TRANSFER — Integration Handoff

Money deducted but not received, a failed/wrong transaction, or a wrong
charge: the customer sees their transactions, existing disputes and tickets,
and can raise a dispute (gathered in chat, **submitted in the app**).
Read `COMMON.md` first.

## Services

| Ask | `category` / `service` | Status |
|---|---|---|
| Transaction history (8.1) | `polygon_services` / `transaction_history` | ✅ Live (see `MINI_STATEMENT.md`) |
| Raise dispute (8.2) | `service_requests` / `raise_dispute` | ✅ Gather + redirect (never POSTs) |
| List disputes (8.3) | `service_requests` / `disputes` | ✅ Live |
| Submit complaint (8.4) | — | ⛔ Blocked |
| My complaints (8.5) | `polygon_services` / `my_tickets` | ✅ Live |

## Raise dispute flow

The bot needs three things, asks for whatever is missing (one question at a
time, LLM-worded), then returns a summary and `routing.action: "raise_dispute"`:

| Field | Type | Meaning |
|---|---|---|
| `accountNumber` | string | The customer's account the transaction was on |
| `transactionReferenceNo` | string | Reference from the transaction / SMS |
| `remarks` | string | What went wrong, in the customer's words |

Triggers (live): "I sent 3000 to my brother yesterday, money was deducted but he
never got it", "ATM took my card money but no cash came out",
"i want to raise a dispute".

## Response — `result`

**Gathering** → `CLARIFICATION_REQUIRED` (bubble asks for the missing pieces).

**Summary** (live):
```json
{"type": "BANKING_SERVICE", "category": "service_requests", "service": "raise_dispute",
 "payload": {"accountNumber": "100126000056", "transactionReferenceNo": "TXN123456",
             "remarks": "3000 taka deducted but never reached my brother", "executed": false},
 "routing": {"category": "service_requests", "service": "raise_dispute", "action": "raise_dispute"}}
```

**Disputes / tickets**: `{"disputes": []}`, `{"complaints": []}`.

## Frontend integration (Dart)

```dart
void renderFailedTransfer(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  if (turn.service == 'raise_dispute' && p['executed'] == false) {
    showDisputeSummaryCard(
      account: maskTail(p['accountNumber']),
      reference: p['transactionReferenceNo'],
      remarks: p['remarks'],
      // The app's own "Dispute a Transaction" screen submits it (POST service-request/v1/disputes).
      onContinue: () => openAppScreen('raise_dispute', prefill: {
        'accountNumber': p['accountNumber'],
        'transactionReferenceNo': p['transactionReferenceNo'],
        'remarks': p['remarks'],
      }),
    );
  }
}
```

Tip: next to the dispute question, offer a "Pick from my transactions" button
that calls `transaction_history` (direct route) and lets the customer tap the
transaction — its reference fills `transactionReferenceNo`, so they don't
have to find it.

## Live-verified (2026-10-03, `taslim_islamic`)

- "I sent 3000 to my brother yesterday, money was deducted but he never got it" → `raise_dispute` gathering ("account number and transaction reference number?").
- "ATM took my card money but no cash came out" → same.
- Full details in one message → summary above, `executed: false`.
- "any open disputes", "status of my dispute" → `disputes`, "There are no open disputes."

## Known gaps

1. Banglish "taka kete nise kintu jay nai" ("money was deducted but didn't go") is still read as a new transfer ("Where do you want to send money?").
2. Customers rarely know a transaction reference; the transaction-picker tip above avoids asking.
