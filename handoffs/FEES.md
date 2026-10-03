# FEES — Integration Handoff

Per-intent handoff for the `FEES` intent (transaction fee/charge quote), one
of the 14 new intents the API team supplied. First of these to be
implemented — see `TASKS.md` T-41/T-42 for full implementation history.

Base connection details (URL, auth header, SSE event shapes) are unchanged
from the main `HANDOFF.md` — this doc only covers what's specific to `FEES`.

## How to trigger it

Two ways, same as every other banking-service intent:

**1. Natural language** — the customer just asks:
- "what's the fee for a bank transfer"
- "how much does it cost to send 500 taka via bKash"
- "what are your fees" (ambiguous — see below)

**2. Direct route** — skip classification, call it explicitly:
```json
{
  "message": "fee check",
  "category": "fees",
  "service": "fee_quote",
  "payload": {"transactionType": "bkash", "amount": 500}
}
```

## Request payload

| Field | Type | Required | Notes |
|---|---|---|---|
| `transactionType` | string | ✅ | One of the bank's live transfer ids (from the Pay & Transfer menu): `bkash`, `nagad`, `rocket`, `upay`, `own_account`, `city_account`, `other_bank`. In chat the customer can say it any way ("bKash", "NPSB", "another bank") — the bot maps it to these ids, and asks if it can't. |
| `amount` | number | ✅ | In **taka** (not poisha) — we convert to poisha internally before calling the bank endpoint. |

Both fields are required — if either is missing, natural-language messages
that don't mention a clear transaction type + amount correctly get a
`CLARIFICATION_REQUIRED` response asking for both.

## Response — `result` event

```json
{
  "type": "BANKING_SERVICE",
  "category": "fees",
  "service": "fee_quote",
  "subservice": null,
  "payload": {
    "principalAmount": 50000,
    "fees": {"charge": 0.0, "vat": 0.0, "total": 0.0},
    "totalAmount": 50000.0
  },
  "routing": {"category": "fees", "service": "fee_quote", "subservice": null, "action": "redirect"},
  "version": "1.0"
}
```

- `principalAmount` / `totalAmount` are in **poisha** (raw, as the bank
  returns them) — divide by 100 for taka if displaying.
- `fees.charge` / `fees.vat` / `fees.total` — the fee breakdown. In this dev
  environment, every transaction type spot-tested so far returns `0` for all
  three (unclear if that's the real production fee schedule or just this
  environment's config — worth confirming with the bank team before
  assuming zero fees in production).
- No `*Masked`/`*Formatted` fields yet — this payload hasn't gone through
  the same masking/formatting pass as accounts/transactions (there's no
  account/card number in this response to mask anyway).

## Frontend integration

**Detecting this result** (with the `PolygonBotClient` from `COMMON.md`):
```dart
if (turn.type == 'BANKING_SERVICE' && turn.service == 'fee_quote') {
  showFeeQuoteCard(turn.payload!);           // below
}
// CLARIFICATION_REQUIRED (type/amount missing) and SERVICE_UNAVAILABLE need
// nothing fee-specific: the bubble text is the whole answer.
```

**What to render on success**: a single small breakdown card, not a table —
this is one quote, not a list. Suggested layout:

```
┌─────────────────────────────┐
│  Fee Quote                  │
│  Principal Amount   ৳500    │
│  Charge              ৳0     │
│  VAT                  ৳0    │
│  ─────────────────────────  │
│  Total                ৳500  │
└─────────────────────────────┘
```

```dart
// Every amount in this payload is POISHA — same as the app's own
// TransactionChargeDto, which parses charge/vat/totalAmount with Money.fromPoisha.
final principal = Money.fromPoisha(payload['principalAmount']?.toString());
final charge = Money.fromPoisha(payload['fees']['charge']?.toString());
final vat = Money.fromPoisha(payload['fees']['vat']?.toString());
final total = Money.fromPoisha(payload['totalAmount']?.toString());
// render with .formattedWithSymbol, as elsewhere in the app
```
**Unit note**: all money fields here are **poisha** (1 taka = 100 poisha).
Confirmed 2026-10-03 against the bank app's `core/data/dto/transaction_charge_dto.dart`.
The chatbot's spoken reply already converts to taka before wording it.

**Action buttons**: none needed. This is informational only — `routing.action`
is always the generic `"redirect"` value here (not a specific navigation
target like `BENEFICIARY_MATCH` gets). If your flow wants a "proceed to
transfer" button after showing the quote, that's your own app's existing
navigation (same transfer screens as always) — we don't provide a routing
hint for it since we never initiate the transfer ourselves.

## Live-verified (2026-09-30, re-checked 2026-10-03)

- `"how much does it cost to send 500 taka via bKash"` → `BANKING_SERVICE`,
  real fee data, correct 500→50000 poisha conversion, coherent spoken reply.
- `"what are your fees"` (no type/amount named) → `CLARIFICATION_REQUIRED`,
  asks which transaction type and amount.
- Direct route with `payload.transactionType`/`payload.amount` → same
  correct behavior, bypassing classification entirely.
- 2026-10-03: "bkash e 5000 pathale koto charge" (Banglish) → quote, Tk 0.00 charge;
  "What would be the total charge if I transfer 20000 taka to another bank via NPSB?" →
  mapped to `other_bank`, quote returned; "is there any charge" → asks type + amount.

## Known gaps

1. The valid `transactionType` ids are read from the live Pay & Transfer menu
   (not hard-coded). Cash-by-code and other menu items without sub-types aren't
   offered for quotes.
2. **Zero fees observed everywhere so far** — likely a dev-environment
   config state, not necessarily representative of production fee amounts.
3. This is a read-only quote — it does **not** execute anything. Same
   ADR-0008 boundary as every other service here: we inform, never move
   money.
