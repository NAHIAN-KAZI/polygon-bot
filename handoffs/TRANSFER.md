# TRANSFER — Integration Handoff

Sending money (gathered in chat, finished in the app), beneficiaries, and
transfer-related lookups. Read `COMMON.md` first.

**The chatbot never moves money.** For a transfer it asks for what's missing
(destination type, account/wallet number, amount), then returns a summary
and the transfer type to show (`routing.action`). The app shows the transfer box in the chat, prefilled from
`payload` (`COMMON.md` §11). The customer presses **Send**, and the app's own transfer use case makes the bank
call with its own PIN/OTP. The bot is never told the outcome.

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

App actions (`APP_ACTION`, inline boxes in the table below; the bot makes no bank call): gift transfer,
email transfer create/cancel/resend, QR pay, beneficiary edit/delete/photo/pin,
transfer-limit changes. Not built: wallet verify (14.15), recipient lookup (14.26).

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 14.1 | Own account transfer | Gather + redirect: `transfer` / `bank_transfer` / `own_account`, `routing.action: "own_account_transfer"` |
| 14.2 | City (Polygon) account transfer | Gather + redirect: `bank_transfer` / `city_account`, `routing.action: "city_account_transfer"` |
| 14.3 | Other bank transfer | Gather + redirect: `bank_transfer` / `other_bank`, `routing.action: "other_bank_transfer"` |
| 14.4 | Other banks list | Not available: app action `other_banks_list`, kind `unavailable` |
| 14.5 | Gift transfer | App action `gift_transfer` → `GiftScreen`, `/gift`. Prefill: `amount`, `recipient` |
| 14.6 | Gifts received | Handled in chat: `transfer_info` / `gifts_received` |
| 14.9 | Email transfer — create | App action `email_transfer_create`. Prefill: `recipientEmail`, `amount` |
| 14.10/14.11 | Email transfers list / detail | Handled in chat: `transfer_info` / `email_transfers` |
| 14.12/14.13 | Email transfer cancel / resend | App action `email_transfer_manage`. Prefill: `action` |
| 14.14 | Wallet transfer | Gather + redirect: `wallet_transfer` / `bkash`·`nagad`·`rocket`·`upay`, `routing.action: "<provider>_transfer"` |
| 14.16/14.17 | QR pay / parse | App action `qr_payment` (camera in the app) |
| 14.18 | QR payment history | Handled in chat: `transfer_info` / `qr_payment_history` |
| 14.19 | Beneficiaries list / send to a saved name | Handled in chat: `polygon_services` / `beneficiary` (`BENEFICIARY_MATCH` / `BENEFICIARY_SELECTION_REQUIRED`) |
| 14.20 | Add beneficiary | Executed in chat after yes/no: `beneficiary_management` / `beneficiary_add` |
| 14.21–14.25 | Beneficiary edit / delete / photo / pin | App actions `beneficiary_edit`, `beneficiary_delete`, `beneficiary_photo`, `beneficiary_pin` |
| 14.27 | My transfer limit | Handled in chat: `transfer_info` / `transfer_limit` |
| 14.28/14.29 | Transfer limit change / cancel pending | App action `transfer_limit_change`. Prefill: `newLimit` |

Wallet verify (14.15) and recipient lookup (14.26) are not built.

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 14.1 | Own account transfer | Gather → inline box | **U8** transfer box: from-account (picker), to-account (the customer's other accounts), amount, note | Send | `amount` (from `payload`) | U7: code + transaction PIN · `POST transfer/v1/bank-transfer/own-account` |
| 14.2 | City Bank transfer | Gather → inline box | **U8** transfer box: from-account, recipient (account or mobile), amount, note | Send | `accountNumber`, `amount` | U7: code + transaction PIN · `POST transfer/v1/bank-transfer/city-bank` |
| 14.3 | Other bank transfer | Gather → inline box | **U8** transfer box: from-account, transfer type (BEFTN, NPSB or RTGS), beneficiary name, account, bank, branch details, amount | Send | `accountNumber`, `amount` | U7: code + transaction PIN · `POST transfer/v1/bank-transfer/other-bank` |
| 14.4 | Other banks list | Not available | **No UI needed.** Bubble only; the bot says it isn't available. | None | None | No backend |
| 14.5 | Gift transfer | App action → inline box | **U8** box: Form: recipient (account or mobile), gift design, wish message, amount. After the button: U7: code + transaction PIN. | Send gift | `amount`, `recipient` (from `ui.prefill`) | App calls `POST transfer/v1/bank-transfer/gift`; shows a local done/failed tile |
| 14.6 | Gifts received | Answered in chat | **U2 gifts** — Gifts received. | None | None | — |
| 14.9 | Email transfer — create | App action → inline box | **U8** box: Form: recipient email, amount, security question and answer. After the button: U7: code + transaction PIN. | Send | `recipientEmail`, `amount` (from `ui.prefill`) | App calls `POST transfer/v1/email-transfer`; shows a local done/failed tile |
| 14.10 | Email transfer — list | Answered in chat | **U2 email transfers** — Email transfers with status. | None | None | — |
| 14.11 | Email transfer — details | Answered in chat | **U3 email transfer** — One email transfer's details. | None | None | — |
| 14.12 | Email transfer — cancel | App action → inline box | **U8** box: The customer's email transfers, each with two buttons. After the button: None. | Cancel (ask to confirm) · Resend | `action` (from `ui.prefill`) | App calls `POST transfer/v1/email-transfer/{id}/cancel` · `.../resend-notification`; shows a local done/failed tile |
| 14.13 | Email transfer — resend | App action → inline box | **U8** box: The customer's email transfers, each with two buttons. After the button: None. | Cancel (ask to confirm) · Resend | `action` (from `ui.prefill`) | App calls `POST transfer/v1/email-transfer/{id}/cancel` · `.../resend-notification`; shows a local done/failed tile |
| 14.14 | Wallet/MFS transfer | Gather → inline box | **U8** wallet box: from-account, wallet provider (from `subservice`) and number, transfer type (direct or NPSB), amount, note | Send | `walletNumber`, `amount` | U7: code + transaction PIN · `POST transfer/v1/wallet-transfer` |
| 14.16 | QR pay | App action → inline box | **U8** box: Scan area (camera) that shows the merchant and amount once read. After the button: U7: code + PIN. | Scan · Pay | None (from `ui.prefill`) | App calls `POST merchant/v1/qr/parse`, then `POST merchant/v1/qr/pay`; shows a local done/failed tile |
| 14.17 | QR parse | App action → inline box | **U8** box: Scan area (camera) that shows the merchant and amount once read. After the button: U7: code + PIN. | Scan · Pay | None (from `ui.prefill`) | App calls `POST merchant/v1/qr/parse`, then `POST merchant/v1/qr/pay`; shows a local done/failed tile |
| 14.18 | QR payment history | Answered in chat | **U2 QR payments** — QR payment history (amounts are already taka). | None | None | — |
| 14.19 | Beneficiary — list | Answered in chat | **Beneficiary cards (existing)** — List; `BENEFICIARY_MATCH` shows one card with **Send** → the transfer box (U8) for the type in `payload.destination` / `routing.action` (`own_bank_transfer`, `other_bank_transfer`, `wallet_transfer` + provider, or manual); several matches use the beneficiary picker. | See text | None | — |
| 14.20 | Beneficiary — add | Executed in chat | U1 asks for name and account number (bank details for another bank) → **U6** (name, account ending, bank) → done notice | Yes / No | None | The bot makes the call after Yes |
| 14.21 | Beneficiary — edit | App action → inline box | **U8** box: Form: beneficiary (preselected by name), nickname field. After the button: None. | Save | `nickname` (from `ui.prefill`) | App calls `PATCH beneficiary/v1/beneficiaries/{id}` with `nickname` (only the nickname is editable); shows a local done/failed tile |
| 14.22 | Beneficiary — delete | App action → inline box | **U8** box: Confirm card with the beneficiary's name and masked account. After the button: None. | Delete · Keep | None (from `ui.prefill`) | App calls `DELETE beneficiary/v1/beneficiaries/{id}`; shows a local done/failed tile |
| 14.23 | Beneficiary — upload/change photo | App action → inline box | **U8** box: Beneficiary (preselected) with a photo area. After the button: None. | Choose photo · Remove photo · Save | None (from `ui.prefill`) | App calls `PATCH beneficiary/v1/beneficiaries/{id}/photo` (multipart) · `DELETE .../photo`; shows a local done/failed tile |
| 14.24 | Beneficiary — remove photo | App action → inline box | **U8** box: Beneficiary (preselected) with a photo area. After the button: None. | Choose photo · Remove photo · Save | None (from `ui.prefill`) | App calls `PATCH beneficiary/v1/beneficiaries/{id}/photo` (multipart) · `DELETE .../photo`; shows a local done/failed tile |
| 14.25 | Beneficiary — pin/unpin | App action → inline box | **U8** box: Beneficiary list with a pin switch each (list pinning, not a security PIN). After the button: None. | Pin switch | None (from `ui.prefill`) | App calls `PATCH beneficiary/v1/beneficiaries/{id}/pin` with `pinned`; shows a local done/failed tile |
| 14.27 | My transfer limit — get | Answered in chat | **U3 limits** — Transfer limits (daily/monthly) as bars; unset values show "Not set". | None | None | — |
| 14.28 | My transfer limit — request change | App action → inline box | **U8** box: Account picker and the new limit, or the pending request. After the button: U7: code + transaction PIN. | Submit · Cancel pending request | `newLimit` (from `ui.prefill`) | App calls `PUT transfer/v1/my-limit/{accountIdentifier}` · `DELETE transfer/v1/my-limit/pending/{requestId}`; shows a local done/failed tile |
| 14.29 | My transfer limit — cancel pending change | App action → inline box | **U8** box: Account picker and the new limit, or the pending request. After the button: U7: code + transaction PIN. | Submit · Cancel pending request | `newLimit` (from `ui.prefill`) | App calls `PUT transfer/v1/my-limit/{accountIdentifier}` · `DELETE transfer/v1/my-limit/pending/{requestId}`; shows a local done/failed tile |
| 14.7 | Generic transaction | Not a customer ask | Nothing: no use case in chat (bank-internal) | None | None | — |
| 14.8 | Linked account check | Not a customer ask | Nothing: no use case in chat (bank-internal) | None | None | — |
| 14.15 | Wallet verify | Not built | Bubble only | None | None | — |
| 14.26 | Recipient lookup by account number | Not built | Bubble only | None | None | — |

<!-- UI-TO-BUILD:END -->

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
Send `"Yes"` + `{"confirm": true}` or `"No"` + `{"confirm": false}`. "No" → `BANKING_SERVICE` with `{"executed": false, "cancelled": true}`.
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
      // U8: the transfer box for `action`, prefilled from `payload` (amount in taka, number as the customer wrote it).
      showTransferBox(action!, prefill: p);
    case 'BENEFICIARY_MATCH':
      final b = (p['beneficiary'] as Map).cast<String, dynamic>();
      showBeneficiaryCard(b, onSend: () => showTransferBox(
          (p['destination'] as Map)['action'], prefill: b));   // U8 box for that beneficiary
    case 'BENEFICIARY_SELECTION_REQUIRED':
      showPicker((p['beneficiaries'] as List).cast<Map<String, dynamic>>(),
          onPick: (b) => onSend('Selected', payload: {'beneficiaryId': b['id']}));
    case 'CONFIRMATION_REQUIRED':
      showYesNo(onYes: () => onSend('Yes', payload: {'confirm': true}),
                onNo: () => onSend('No', payload: {'confirm': false}));
    case 'BANKING_SERVICE' when turn.service == 'transfer_limit':
      showLimitBars(p, money: (v) => v == null ? 'Not set' : Money.fromPoisha(v).format());
    case 'BANKING_SERVICE' when turn.service == 'qr_payment_history':
      showQrHistory((p['data'] as List), money: (v) => 'Tk $v'); // already taka
    default:
      break;
  }
}
```

Rendering: the transfer summary opens the transfer box (U8) with one primary
button (**Send**), prefilled from `payload`; limits as three small progress bars
(daily/weekly/per transaction); histories as lists.

## Live-verified (2026-10-03, `taslim_islamic`)

- Wallet (English + Banglish), other bank, own accounts, vague "send money" — all correct.
- Limit, gifts, email transfers, QR history, beneficiary list — real (mostly empty) data.
- Add beneficiary: asks for name + account, confirms with masked ending, "no" cancels.

## Known gaps

1. **Add beneficiary**: after "yes" the bank returns `500 An internal error occurred` for both `OTHER_BANK` and `OWN_BANK` bodies. Waiting on the API team for the required fields per `serviceType`. Until then a "yes" shows `SERVICE_UNAVAILABLE`.
2. Own-account transfer (14.1) with only one account: the bot answers that there is no other account to move money to (`BANKING_SERVICE`, `executed: false`, no `routing.action`): show the bubble only, no box. With two or more accounts it asks which one (`ACCOUNT_SELECTION_REQUIRED`) and then the box applies.
3. For an other-bank transfer the bank name, branch and transfer type (BEFTN, NPSB, RTGS) are not in `payload`: the customer picks them in the box.
4. Wallet verify and recipient lookup not built.
