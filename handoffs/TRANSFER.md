# TRANSFER — Integration Handoff

Sending money (gathered in chat, finished in the app), beneficiaries, and
transfer-related lookups. Read `COMMON.md` first.

**The chatbot never moves money.** For a transfer it asks for what's missing
(destination type, account/wallet number, amount), then returns a summary
and the screen to finish it on (`routing.action`). The customer confirms in
the app's own transfer screen, with its own PIN/OTP.

## Services

| Ask | `category` / `service` / `subservice` | Status |
|---|---|---|
| Own account transfer (14.1) | `transfer` / `bank_transfer` / `own_account` | ✅ Gather + redirect |
| Polygon (City) account transfer (14.2) | `transfer` / `bank_transfer` / `city_account` | ✅ Gather + redirect |
| Other bank transfer (14.3) | `transfer` / `bank_transfer` / `other_bank` | ✅ Gather + redirect |
| Wallet transfer (14.14) | `transfer` / `wallet_transfer` / `bkash`·`nagad`·`rocket`·`upay` | ✅ Gather + redirect |
| Send to a saved beneficiary by name | `polygon_services` / `beneficiary` | ✅ Live (match + redirect) |
| Beneficiary list (14.19) | `polygon_services` / `beneficiary` | ✅ Live |
| Add beneficiary (14.20) | `beneficiary_management` / `beneficiary_add` | ⛔ Chat flow works; bank returns 500 on the add (see gaps) |
| Transfer limit (14.27) | `transfer_info` / `transfer_limit` | ✅ Live |
| Gifts received (14.6) | `transfer_info` / `gifts_received` | ✅ Live |
| Email transfers list/detail (14.10/14.11) | `transfer_info` / `email_transfers` | ✅ Live |
| QR payment history (14.18) | `transfer_info` / `qr_payment_history` | ✅ Live |

Blocked (they change data; the bot says to use the app): gift transfer,
email transfer create/cancel/resend, QR pay, beneficiary edit/delete/photo/pin,
limit change requests. Not built: wallet verify (14.15), recipient lookup (14.26).

## How to trigger

Live-tested: "send money" (→ "Where do you want to send the money?"),
"send 1500 taka to my bkash 01711223344", "nagad e 2000 pathabo 01811223344",
"transfer 10000 to my brac bank account 1234567890123",
"move 5000 between my own accounts", "whats my daily transfer limit",
"did i get any gifts", "email transfer status", "qr payments i made",
"who are my saved beneficiaries", "add a new beneficiary".

## Request payload (direct route)

| Service | Field | Type | Notes |
|---|---|---|---|
| `bank_transfer` | `accountNumber` | string | Destination account |
| `bank_transfer`, `wallet_transfer` | `amount` | number | **Taka** (what the customer typed) |
| `wallet_transfer` | `walletNumber` | string | Destination wallet; provider = `subservice` |
| `beneficiary` | `nameQuery` | string | Saved beneficiary nickname/name |
| `beneficiary_add` | `nickname`, `accountNumber` | string | Both required before the yes/no |
| `email_transfers` | `tab`, `page`, `size` | — | Optional list filters |

Missing fields are asked for in chat (`CLARIFICATION_REQUIRED`), one turn at a time.

## Response — `result`

**Wallet transfer summary** (live). `executed` is always `false`:
```json
{"type": "BANKING_SERVICE", "category": "transfer", "service": "wallet_transfer", "subservice": "bkash",
 "payload": {"amount": "1500", "walletNumber": "01711223344", "formattedAmount": "৳1,500", "executed": false},
 "routing": {"category": "transfer", "service": "wallet_transfer", "subservice": "bkash", "action": "bkash_transfer"}}
```

**Bank transfer summary** (live):
```json
{"type": "BANKING_SERVICE", "category": "transfer", "service": "bank_transfer", "subservice": "other_bank",
 "payload": {"accountNumber": "1234567890123", "amount": "10000", "formattedAmount": "৳10,000", "executed": false},
 "routing": {"action": "other_bank_transfer", "...": "..."}}
```
`routing.action` is `<subservice>_transfer`: `own_account_transfer`,
`city_account_transfer`, `other_bank_transfer`, `bkash_transfer`,
`nagad_transfer`, `rocket_transfer`, `upay_transfer`. Map each to your transfer
screen and pre-fill amount/number from `payload`.

**Beneficiary match** (send to a saved person): `type: "BENEFICIARY_MATCH"`,
`payload: {"beneficiary": {...}, "destination": {"action": "own_bank_transfer" | "other_bank_transfer" | "wallet_transfer", "provider"?: "bkash"}}`.
Several matches → `type: "BENEFICIARY_SELECTION_REQUIRED"` (`payload.beneficiaries`,
pick one and send `payload: {"beneficiaryId": <id>}`). No match → `CLARIFICATION_REQUIRED`
saying so.

**Beneficiary list** (live): `{"beneficiaries": []}`.

**Add beneficiary** — a yes/no step (live):
```json
{"type": "CONFIRMATION_REQUIRED", "category": "beneficiary_management", "service": "beneficiary_add",
 "payload": {"nickname": "ClaudeTestDeleteMe", "accountNumber": "100126000015",
             "serviceType": "OTHER_BANK", "identifierType": "ACCOUNT_NUMBER"}}
```
Send `"yes"` / `"no"`. "no" → `BANKING_SERVICE` with `{"executed": false, "cancelled": true}`.
Only an explicit yes calls the bank.

**Transfer limit** (live; money fields poisha, `null` = not set):
```json
{"accountIdentifier": "100126000056", "usedToday": 0,
 "daily":   {"current": null, "bankMax": null, "riskAdjustedMax": null, "used": 0, "pendingChange": null},
 "weekly":  {"current": null, "bankMax": null, "riskAdjustedMax": null, "used": 11000000, "pendingChange": null},
 "perTransaction": {"current": null, "bankMax": null, "riskAdjustedMax": null, "used": null, "pendingChange": null}}
```

**Gifts / email transfers** (live): `{"items": [], "pagination": {...}}`.
**QR history** (live): `{"data": []}` — amounts here are already **taka**.

## Frontend integration (Dart)

```dart
void renderTransfer(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  final action = (turn.result?['routing'] as Map?)?['action'] as String?;
  switch (turn.type) {
    case 'BANKING_SERVICE' when turn.category == 'transfer':
      // Summary card + "Continue in app" -> your transfer screen, pre-filled.
      showTransferSummary(
        amount: p['formattedAmount'],
        to: p['walletNumber'] ?? maskTail(p['accountNumber']),
        onContinue: () => openTransferScreen(action!, prefill: p),
      );
    case 'BENEFICIARY_MATCH':
      final b = (p['beneficiary'] as Map).cast<String, dynamic>();
      showBeneficiaryCard(b, onSend: () => openTransferScreen(
          (p['destination'] as Map)['action'], prefill: b));
    case 'BENEFICIARY_SELECTION_REQUIRED':
      showPicker((p['beneficiaries'] as List).cast<Map<String, dynamic>>(),
          onPick: (b) => onSend('Selected', payload: {'beneficiaryId': b['id']}));
    case 'CONFIRMATION_REQUIRED':
      showYesNo(onYes: () => onSend('yes'), onNo: () => onSend('no'));
    case 'BANKING_SERVICE' when turn.service == 'transfer_limit':
      showLimitBars(p, money: (v) => v == null ? 'Not set' : Money.fromPoisha(v).format());
    case 'BANKING_SERVICE' when turn.service == 'qr_payment_history':
      showQrHistory((p['data'] as List), money: (v) => 'Tk $v'); // already taka
    default:
      break;
  }
}
```

Rendering: transfer summary as a confirmation-style card with one primary
button ("Continue in app"); limits as three small progress bars
(daily/weekly/per transaction); histories as lists.

## Live-verified (2026-10-03, `taslim_islamic`)

- Wallet (English + Banglish), other bank, own accounts, vague "send money" — all correct.
- Limit, gifts, email transfers, QR history, beneficiary list — real (mostly empty) data.
- Add beneficiary: asks for name + account, confirms with masked ending, "no" cancels.

## Known gaps

1. **Add beneficiary**: after "yes" the bank returns `500 An internal error occurred` for both `OTHER_BANK` and `OWN_BANK` bodies. Waiting on the API team for the required fields per `serviceType`. Until then a "yes" shows `SERVICE_UNAVAILABLE`.
2. "move 5000 between my own accounts" asks for an account even when the customer has only one.
3. Wallet verify and recipient lookup not built.
