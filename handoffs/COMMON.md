# Common — Chat API contract and shared Dart client

Every per-intent handoff in this folder builds on this page: one Dart client,
one result envelope, and the generic result types every intent can return.
Connection details (base URL, API key) are in `INTEGRATION.md`.

## 0. Rule: drive the UI from data, never from bubble text

Every customer-facing message is written by the language model from structured
facts, so the same step is worded differently from turn to turn. **Never match
on bubble text.** Decide what to render only from `result.type`, `category`,
`service`, `subservice`, `payload` and `routing`.

The one fixed sentence is the fallback when the bot's language model can't be
reached: `"Sorry, I'm having trouble right now. Please try again in a moment."`
The `result` event that follows still carries the real outcome, so render from it as usual.

## 1. Request

`POST /chat`, headers `X-API-Key: <key>`, `Content-Type: application/json`,
and `Authorization: Bearer <customer JWT>` for anything account-related.

| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | string | ✅ | 1–4000 chars: what the customer typed, or a short label (`"Yes"`, `"Selected"`, `"Verify"`) when the app sends a structured answer |
| `category`, `service`, `subservice` | string | — | Pass `category`+`service` together to call one service directly (ids as in each intent doc). **Leave them out when answering an open question** (§5): a request with `category`+`service` counts as a new request, and the pending one is dropped |
| `payload` | object | — | Structured answers (picked account/card/transaction, yes/no, the verification form) or direct-route fields |

The customer's identity always comes from the JWT. The bot keeps a short
per-customer conversation, so a typed follow-up ("the savings one", "500",
"yes") is understood in context. The app only sends the next message.

## 2. Response stream (SSE)

`text/event-stream`, in this order:

1. `event: token` — `{"token": "..."}`, one or more. Concatenate them: this is the
   chat bubble text (English).
2. `event: result` — exactly one, the structured outcome (§3).
3. `event: done` — `{}`. Close the stream.

**Errors.** `event: error` with `{"detail": "<reason>"}` can end the stream
instead of `result`/`done`. Today it only comes from the knowledge-base path (embedding model,
vector store or generation unreachable). Read the `detail` field (there is no `message`
field), mark the bubble incomplete and offer **Retry** (resend the same request).
Always handle both `done` and `error`, because a stream is not guaranteed to reach `done`.

## 3. `result` envelope

```json
{"type": "BANKING_SERVICE", "category": "account_info", "service": "balance",
 "subservice": null, "payload": {...} | null, "routing": {...} | null, "version": "1.0"}
```

| `type` | Meaning | What the app should do |
|---|---|---|
| `BANKING_SERVICE` | A service answered with data, a gather-only flow finished (transfer/dispute summary), or an approved change ran (`payload.executed: true`) or didn't (`executed: false`, maybe `cancelled: true`) | Show the bubble. Render `payload` as a card/table where the intent doc says so |
| `APP_ACTION` | The request is something the chat does not carry out. The app has the screen for it, or it isn't available. No bank call was made | Show the bubble plus an info card from `payload.ui`, with an **Open** button only when the route is openable (§8) |
| `CLARIFICATION_REQUIRED` | The bot asked a question. It may list concrete options in the text ("check your balance or see recent transactions?") | Show the bubble and keep the input open. `category`/`service`/`payload` are `null`. Options are text only. The customer answers by typing |
| `ACCOUNT_SELECTION_REQUIRED` | Several accounts/cards, so the bot asked which one | Bubble plus a picker from `payload.accounts` (§6) |
| `TRANSACTION_SELECTION_REQUIRED` | A dispute needs to know which recent transaction it's about | Bubble plus a picker from `payload.transactions` (§6) |
| `CONFIRMATION_REQUIRED` | An approved change is ready and needs an explicit yes/no | Bubble plus **Yes** / **No** buttons (§7) |
| `OTP_REQUIRED` | A verification code was sent to the customer's registered phone | Open the secure verification form (§7). Never collect codes in the chat box |
| `BENEFICIARY_MATCH` | "Send money to <name>" matched one saved beneficiary | Beneficiary card plus a "Send" button to the transfer screen (`TRANSFER.md`) |
| `BENEFICIARY_SELECTION_REQUIRED` | Several beneficiaries match the name | Picker from `payload.beneficiaries` (`TRANSFER.md`) |
| `KB_ANSWER` | Product/policy answer from the bank's knowledge base, or a polite off-topic decline | Bubble. `payload`: `{"grounded", "hitCount", "sources"}` (`sources` may be `null`) |
| `UNKNOWN_SERVICE` | A direct route named a `category`/`service`/`subservice` that doesn't exist | Bubble. Check the ids you sent |
| `SERVICE_UNAVAILABLE` | The bank's service failed or isn't available for this customer. `payload` is `null` | Bubble plus **Retry** (resend the customer's last request) |
| `AUTH_REQUIRED` | JWT missing, expired or rejected. `payload` is `null` | Refresh the token or send the customer to log in, then offer **Retry** |

Treat any `type` you don't know as "bubble only". Payloads only ever gain fields (additive),
so ignore keys you don't use.

### `routing`

`routing` is `{category, service, subservice, action}` or `null`. `action` names
where the request continues in the app:

| `routing.action` | Comes with | Meaning |
|---|---|---|
| `redirect` | data answers, executed changes | Generic "open in app" target for this service (optional chip) |
| `own_account_transfer`, `city_account_transfer`, `other_bank_transfer`, `bkash_transfer`, `nagad_transfer`, `rocket_transfer`, `upay_transfer` | transfer summary (`executed: false`) | Finish the transfer on that screen (`TRANSFER.md`) |
| `raise_dispute` | dispute summary (`executed: false`) | Finish the dispute on the app's dispute screen (`FAILED_TRANSFER.md`) |
| `start_transfer` | fee quote | Offer to start the matching transfer. `routing.transfer` = `{category, service, subservice, prefill: {amount}}` (`FEES.md`) |
| `report_lost_card` | lost/stolen card (`executed: false`) | Open the app's report-lost-card screen (`LOST_OR_STOLEN_CARD.md`) |
| `update_profile_image` | profile photo (`executed: false`) | Open the app's profile-photo screen |
| `own_bank_transfer`, `other_bank_transfer`, `wallet_transfer`, `manual` | `BENEFICIARY_MATCH` | Transfer screen for that beneficiary (`TRANSFER.md`) |
| `<action id>` | `APP_ACTION` | Same as `service`. Use `payload.ui` (§8) |

The chatbot never executes transfers or disputes itself.

## 4. What the bot does with a request

Every request ends in exactly one of these outcomes. Each intent doc lists its own
requests under "What the bot does for each request in this intent".

| Outcome | `result` | Bank call by the bot |
|---|---|---|
| **Handled in chat** (data answer) | `BANKING_SERVICE` with the data | read-only (GET) |
| **Executed in chat** after yes/no or a code (approved changes only) | `CONFIRMATION_REQUIRED` / `OTP_REQUIRED`, then `BANKING_SERVICE` with `executed` | yes, only after the yes / verified code |
| **Gather + redirect** | `CLARIFICATION_REQUIRED` until complete, then `BANKING_SERVICE` summary with `executed: false` and `routing.action` | none |
| **App action** | `APP_ACTION` (§8) | none |
| **Not available** | `APP_ACTION` with `ui.kind: "unavailable"`, or a clarifying question when chat has no service for it | none |

The approved in-chat changes are exactly these:

| Change | `category` / `service` | Gate |
|---|---|---|
| Add beneficiary | `beneficiary_management` / `beneficiary_add` | yes/no |
| Change nickname | `profile_update` / `update_nickname` | yes/no |
| Change address | `profile_update` / `update_address` | yes/no |
| Submit complaint | `support` / `submit_complaint` | yes/no |
| Freeze card | `card_services` / `frezz_unfrezz` | yes/no, **then** code + card PIN or login password |
| Change mobile number | `profile_update` / `update_mobile` | code (sent to the current registered phone). The customer is signed out afterwards |
| Change email | `profile_update` / `update_email` | code (sent to the current registered phone) |

Everything else that changes data, including unfreeze, PIN reset, close card, card
applications, limit changes, KYC, email transfer, QR pay, beneficiary
edit/delete/pin/photo and transfer-limit changes, is an `APP_ACTION`.

## 5. Answering an open question

While the last result was a question (`*_SELECTION_REQUIRED`, `CONFIRMATION_REQUIRED`,
`OTP_REQUIRED`), the next request answers it. Send these **without** `category`/`service`.
The pending request then resumes.

| Customer action | `message` | `payload` |
|---|---|---|
| Yes / No button | `Yes` / `No` | `{"confirm": true}` / `{"confirm": false}` |
| Verification form submit | `Verify` | freeze: `{"otp", "pin"}` or `{"otp", "password"}`. After `otpRequired: false`: `{"pin"}` or `{"password"}`. Email/mobile: `{"otp"}` |
| Cancel the verification form | `cancel` | `{"confirm": false}` |
| Pick a bank account | `Selected` | `{"accountNumber": <as received>}` |
| Pick a card | `Selected` | `{"cardId": <entry id>}` |
| Pick an FD/DPS ledger account | `Selected` | `{"identifier": <identifier>}` (`{"id": <identifier>}` also works) |
| Pick a transaction | `Selected` | `{"transactionId": <transactionId>}` |

The backend decides yes/no on the `confirm` boolean alone, without reading the text. Typed replies
("yes go ahead", "the savings one", "ending 0015") also work, because the model reads them, but the
structured answers are exact. A typed message that is a different request ("what's my
balance?") drops the pending step. Nothing is executed, and the new request is answered.

## 6. Pickers

### Account / card (`ACCOUNT_SELECTION_REQUIRED`)

`payload.accounts` holds one of three entry shapes:

| Entry | Fields | Send back |
|---|---|---|
| Bank account | `{"accountNumber", "accountName", "accountType", ...}` (may also carry `id`, `balance`) | `{"accountNumber": ...}` |
| Card | `{"id", "cardNumber" (masked), "cardType", ...}` | `{"cardId": <id>}` |
| Ledger (FD/DPS) | `{"identifier", "chartOfAccountName", ...}` | `{"identifier": ...}` |

```json
{"type": "ACCOUNT_SELECTION_REQUIRED", "category": "account_info", "service": "balance",
 "payload": {"accounts": [
   {"accountNumber": "100126000015", "accountName": "Ahad", "accountType": "SAVINGS"},
   {"accountNumber": "100126000056", "accountName": "Ahad", "accountType": "CURRENT"}]}}
```

Show only the last 4 digits of any number. Send the full value back as received.

### Transaction (`TRANSACTION_SELECTION_REQUIRED`, dispute flow)

```json
{"type": "TRANSACTION_SELECTION_REQUIRED", "category": "service_requests", "service": "raise_dispute",
 "payload": {"transactions": [
   {"transactionId": "20260929160519764-…", "txnTime": "2026-09-29T10:05:20Z",
    "type": "DEBIT", "amount": 500000, "transactionType": "bKash"}]}}
```

At most 8 recent transactions. `amount` is **poisha** (divide by 100). `type` is
`DEBIT`/`CREDIT`. The pick becomes the dispute's `transactionReferenceNo`.

## 7. Confirmation and verification

### `CONFIRMATION_REQUIRED`

`payload` holds the values that will be saved, for an optional detail card:

| `service` | `payload` |
|---|---|
| `beneficiary_add` | `nickname`, `accountNumber`, `serviceType` (`OWN_BANK`/`OTHER_BANK`), plus `identifierType`, `accountHolderName` (own bank) or `bankName`, `branchName`, `routingNumber` (other bank) |
| `update_nickname` | `nickName` |
| `update_address` | any of `presentAddress`, `permanentAddress`, `district`, `division` |
| `submit_complaint` | `category` (`ACCOUNT`, `CARD`, `TRANSACTION`, `LOAN_DEPOSIT`, `MOBILE_APP_TECHNICAL`, `SERVICE_QUALITY`, `OTHER`), `description` |
| `frezz_unfrezz` | `cardId`, `cardLast4`, `reason` (the customer's words). **No code has been sent yet.** Yes sends it |

Outcomes after the answer:
- Yes → `BANKING_SERVICE` with the bank's response plus `executed: true` and
  `routing.action: "redirect"`. For freeze, Yes leads to `OTP_REQUIRED` instead.
- No → `BANKING_SERVICE` with `{"executed": false, "cancelled": true}`.
- Unclear → the same `CONFIRMATION_REQUIRED` again.
- The bank refuses or fails → `SERVICE_UNAVAILABLE` (the bubble passes on a readable bank message).

### `OTP_REQUIRED`

A code was sent to the customer's **current registered phone**. Open a secure form and
submit it as a structured payload (§5). Never as chat text, and never logged by the app.

```json
{"type": "OTP_REQUIRED", "category": "card_services", "service": "frezz_unfrezz",
 "payload": {"cardId": "45", "cardLast4": "0293", "reason": "my card was stolen",
             "otpRequired": true, "credentialOptions": ["pin", "password"],
             "verificationStatus": "OTP_SENT"}}
```

| Flow | Form fields | Extra payload |
|---|---|---|
| Card freeze (`card_services`/`frezz_unfrezz`) | code + **one** of card PIN or login password (`credentialOptions: ["pin", "password"]`) | `cardId`, `cardLast4`, `reason` |
| Mobile change (`profile_update`/`update_mobile`) | code only (`credentialOptions: []`) | `newPhone` |
| Email change (`profile_update`/`update_email`) | code only (`credentialOptions: []`) | `newEmail` |

`otpRequired: false` means the code was accepted and only the PIN/password is
re-asked (hide the code field). `attemptsRemaining` comes with `OTP_INCORRECT`.

`verificationStatus` while the form stays open (`OTP_REQUIRED` again):

| Status | Meaning |
|---|---|
| `OTP_SENT` | First code sent |
| `OTP_RESENT` | The earlier code expired (or the verification lapsed), so a new code was sent |
| `CREDENTIALS_MISSING` | The code (or, for freeze, the PIN/password) wasn't submitted |
| `CREDENTIALS_INVALID_COMBINATION` | Freeze: both PIN and password sent. Send one |
| `OTP_INCORRECT` | Wrong code. Re-enter the same code. `attemptsRemaining` included |
| `INVALID_CREDENTIALS` | Freeze: wrong PIN/password. The code is still valid (`otpRequired: false`) |

Terminal outcomes (the form closes):
- Done → `BANKING_SERVICE`, `executed: true`. Freeze: `{"executed": true, "cardId", "cardLast4", "status"}`.
  Email/mobile: `{"executed": true, "newEmail" | "newPhone"}`. After a mobile change the
  customer is signed out.
- Not done → `BANKING_SERVICE`, `executed: false` with `verificationStatus` `SEND_THROTTLED`
  (too many codes requested) or `OTP_BLOCKED` (freeze: too many wrong codes), or
  `bankMessage` (email/mobile refused by the bank).
- Cancelled → `BANKING_SERVICE`, `{"executed": false, "cancelled": true}`.
- Bank failure → `SERVICE_UNAVAILABLE`. Expired login → `AUTH_REQUIRED`.

A plain chat message that isn't a cancel (for example "what's my balance") leaves the step. Nothing
is changed and the message is answered as a new request.

## 8. `APP_ACTION` — requests the chat does not carry out

> **Presentation:** the primary design is the inline box in §11 (the customer finishes inside the chat). The Open / Info only labels in this section and in the intent files describe the optional fallback button (U11).

```json
{"type": "APP_ACTION", "category": "app_actions", "service": "card_limit_change", "subservice": null,
 "payload": {"ui": {"kind": "screen", "title": "Change card limit",
                    "screen": "CardLimitChangeScreen", "route": "/card_limit_change_request",
                    "prefill": {"cardLast4": "0251", "requestedLimit": 50000},
                    "needs": "choose the credit card and enter the new limit they want; the bank reviews it"},
             "executed": false},
 "routing": {"category": "app_actions", "service": "card_limit_change", "subservice": null,
             "action": "card_limit_change"}}
```

| `ui` field | Meaning |
|---|---|
| `kind` | `screen`: the app has a screen for it. `info`: show information only. `unavailable`: the bank has no backend for it |
| `title` | Short name for the card header |
| `screen` | Flutter screen class (may be `null`) |
| `route` | App route path, or `null` (bottom sheet / nested screen) |
| `prefill` | Optional fields **the customer actually wrote** (values the bot couldn't find in their message are dropped), or `null`. Amounts are taka |
| `needs` | Plain description of what the customer does there (the bubble already words it) |

**Dart handling:**
- Show an info card with `title` (and `needs` if you like).
- Show an **Open** button only when `kind == "screen"` and `route` is a plain
  openable path. On tap (never automatically): `Get.toNamed(route, arguments: prefill)`.
- Information only (no button) when `kind` is `info`/`unavailable`, when `route` is `null`,
  when it has a `:` placeholder (`/card_payment/details/:type`), or when it is one of the three routes
  whose screens need a specific object as their argument and would crash on a map:
  `/card_detail`, `/card_limit_change_request` (`CardAccount`), `/request_card_replacement`
  (`CardReplacementArgs`).
- `prefill` is passed as `Get.arguments` (a `Map<String, dynamic>` or `null`). Most target
  screens don't read it yet. They can adopt it with `if (Get.arguments is Map) ...`.

### Registry (29 actions, `app/banking/ui_actions.py`)

"Rows" are the `planning/input/INTENT_IMPLEMENTATION_STATUS.md` rows each action covers.
"In app" applies the rule above.

| `service` (action id) | Title | kind | Screen | Route | In app | Prefill fields | Rows |
|---|---|---|---|---|---|---|---|
| `card_pin_reset` | Reset card PIN | screen | `SelectCardForPinResetScreen` | `/set_reset_card_pin` | Open | `cardLast4` | 3.1, 4.6 |
| `card_unfreeze` | Unfreeze card | screen | `FreezeCardScreen` | `/freeze_card` | Open | `cardLast4` | 3.2, 4.2 |
| `card_close` | Close card | screen | `CardReplacementScreen` | `/request_card_replacement` | Info only | `cardLast4` | 4.3 |
| `card_contactless` | Contactless on/off | screen | `CardDetailScreen` | `/card_detail` | Info only | `cardLast4` | 4.4 |
| `card_international` | International use on/off | screen | `SelectCardForInternationalScreen` | `/international_transaction/select_card` | Open | `cardLast4` | 4.5 |
| `card_limit_change` | Change card limit | screen | `CardLimitChangeScreen` | `/card_limit_change_request` | Info only | `cardLast4`, `requestedLimit` | 4.7 |
| `card_limit_cancel` | Cancel limit change | screen | `CardLimitChangeScreen` | `/card_limit_change_request` | Info only | — | 4.9 |
| `card_apply` | Apply for a card | screen | `CardProductCatalogScreen` | `/card_product_catalog` | Open | `cardType` | 4.11, 4.13, 4.15 |
| `card_virtual_cancel` | Cancel virtual card | info | — | — | Info only | — | 4.17 |
| `card_details_reveal` | Show full card details | info | `CardDetailScreen` | `/card_detail` | Info only | — | 4.12, 4.14, 4.18, 5.3 |
| `credit_card_pay` | Pay credit card bill | screen | `CardDetailScreen` | `/card_detail` | Info only | `paymentType` | 4.20 |
| `other_card_pay` | Pay another bank's card bill | screen | `CardPaymentDetailsScreen` | `/card_payment/details/:type` | Info only | `amount`, `cardNumberLast4` | 4.21 |
| `replacement_cancel` | Cancel card replacement | screen | `CardReplacementScreen` | `/request_card_replacement` | Info only | — | 5.2 |
| `quick_view_star` | Star account or card | screen | `CustomizeQuickViewScreen` | `/customize_quick_view` | Open | — | 1.5, 4.19 |
| `kyc_submit` | Submit KYC documents | screen | `UpdateKycScreen` | `/profile/update_kyc` | Open | `occupation` | 7.9 |
| `profile_change_request` | Request a profile detail change | screen | `ProfileChangeRequestScreen` | `/profile_change_request` | Open | `fieldName`, `requestedValue`, `reason` | 7.11 |
| `contact_priority_change` | Change primary contact | screen | `ContactPriorityScreen` | `/contact_priority` | Open | `reason` | 7.13 |
| `cash_by_code` | Cash by code | screen | `CashByCodeScreen` | `/cash_by_code` | Open | `amount`, `recipientMobile` | 2.1 |
| `gift_transfer` | Send a gift | screen | `GiftScreen` | `/gift` | Open | `amount`, `recipient` | 14.5 |
| `email_transfer_create` | Send money by email | screen | `EmailTransferEntryScreen` | `/email_transfer/entry` | Open | `recipientEmail`, `amount` | 14.9 |
| `email_transfer_manage` | Cancel or resend an email transfer | screen | `EmailTransferListScreen` | `/email_transfer/list` | Open | `action` | 14.12, 14.13 |
| `qr_payment` | Pay by QR code | screen | `QrScanScreen` | — | Info only | — | 14.16, 14.17 |
| `beneficiary_edit` | Edit a beneficiary | screen | `BeneficiaryFormScreen` | `/beneficiary/form` | Open | `nickname` | 14.21 |
| `beneficiary_delete` | Delete a beneficiary | screen | `BeneficiaryScreen` | `/beneficiary` | Open | — | 14.22 |
| `beneficiary_pin` | Pin a beneficiary | screen | `BeneficiaryScreen` | `/beneficiary` | Open | — | 14.25 |
| `beneficiary_photo` | Beneficiary photo | screen | `BeneficiaryFormScreen` | `/beneficiary/form` | Open | — | 14.23, 14.24 |
| `transfer_limit_change` | Change transfer limit | screen | `TransferLimitScreen` | `/transfer_limit` | Open | `newLimit` | 14.28, 14.29 |
| `qr_payment_cards` | QR payment cards | unavailable | — | — | Info only | — | 4.22, 4.23 |
| `other_banks_list` | List of other banks | unavailable | — | — | Info only | — | 14.4 |

## 9. Money, numbers, privacy

- Bank amounts in `payload` are **poisha** (1 Tk = 100 poisha), exactly as the bank
  returns them. Use your existing `Money.fromPoisha`. Exception: QR payment
  history is already taka. Fields ending in `Formatted` are ready-to-show taka.
- Amounts the **customer** typed (transfer summaries, fee-quote request, `APP_ACTION` prefill) are taka.
- The bubble text never contains a full account or card number. `payload` may contain one
  (it is the customer's own data, for the app's own rendering), so mask it on screen.


## 10. Dart client (shared by every intent doc)

Uses `package:http` streaming and manual SSE parsing.

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class ChatTurnResult {
  final String text;                       // concatenated `token` events
  final Map<String, dynamic>? result;      // the `result` event
  final String? error;                     // `detail` of an `error` event
  ChatTurnResult(this.text, this.result, {this.error});
  String? get type => result?['type'] as String?;
  String? get category => result?['category'] as String?;
  String? get service => result?['service'] as String?;
  Map<String, dynamic>? get payload =>
      (result?['payload'] as Map?)?.cast<String, dynamic>();
  Map<String, dynamic>? get routing =>
      (result?['routing'] as Map?)?.cast<String, dynamic>();
}

class PolygonBotClient {
  PolygonBotClient(this.baseUrl, this.apiKey, this.jwtProvider);
  final String baseUrl;
  final String apiKey;
  final Future<String?> Function() jwtProvider;

  Future<ChatTurnResult> send(String message,
      {Map<String, dynamic>? payload, String? category, String? service,
       void Function(String partial)? onToken}) async {
    final jwt = await jwtProvider();
    final req = http.Request('POST', Uri.parse('$baseUrl/chat'))
      ..headers.addAll({
        'X-API-Key': apiKey,
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        if (jwt != null) 'Authorization': 'Bearer $jwt',
      })
      ..body = jsonEncode({
        'message': message,
        if (payload != null) 'payload': payload,
        if (category != null) 'category': category,
        if (service != null) 'service': service,
      });

    final res = await http.Client().send(req);
    final text = StringBuffer();
    Map<String, dynamic>? result;
    String? error;
    String? event;
    await for (final line in res.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter())) {
      if (line.startsWith('event: ')) {
        event = line.substring(7);
      } else if (line.startsWith('data: ')) {
        final data = jsonDecode(line.substring(6)) as Map<String, dynamic>;
        if (event == 'token') {
          text.write(data['token']);
          onToken?.call(text.toString());
        } else if (event == 'result') {
          result = data;
        } else if (event == 'error') {
          error = data['detail'] as String?;   // the field is `detail`
        } else if (event == 'done') {
          break;
        }
      }
    }
    return ChatTurnResult(text.toString(), result, error: error);
  }
}
```

Typical dispatch in the chat screen (each intent doc adds its own rendering).
Note that answers to open questions never send `category`/`service`:

```dart
const _needsObject = {'/card_detail', '/card_limit_change_request', '/request_card_replacement'};

bool isOpenableRoute(String? route) =>
    route != null && route.startsWith('/') && !route.contains(':') && !_needsObject.contains(route);

Future<void> onSend(String message, {Map<String, dynamic>? payload,
    String? category, String? service}) async {
  final turn = await bot.send(message, payload: payload, category: category, service: service,
      onToken: (partial) => showTypingBubble(partial));
  if (turn.error != null) {
    showBotBubble(turn.text, incomplete: true);
    showRetry(() => onSend(message, payload: payload, category: category, service: service));
    return;
  }
  showBotBubble(turn.text);   // never parsed: render only from the fields below
  final p = turn.payload ?? const {};
  switch (turn.type) {
    case 'ACCOUNT_SELECTION_REQUIRED':
      showPicker((p['accounts'] as List).cast<Map<String, dynamic>>(), onPick: (a) =>
          onSend('Selected', payload: a.containsKey('cardNumber')
              ? {'cardId': a['id']}
              : a.containsKey('accountNumber')
                  ? {'accountNumber': a['accountNumber']}
                  : {'identifier': a['identifier']}));
    case 'TRANSACTION_SELECTION_REQUIRED':
      showTransactionPicker((p['transactions'] as List).cast<Map<String, dynamic>>(),
          amount: (t) => Money.fromPoisha(t['amount']),   // poisha
          onPick: (t) => onSend('Selected', payload: {'transactionId': t['transactionId']}));
    case 'CONFIRMATION_REQUIRED':
      showYesNo(details: p,
          onYes: () => onSend('Yes', payload: {'confirm': true}),
          onNo: () => onSend('No', payload: {'confirm': false}));
    case 'OTP_REQUIRED':
      final form = await showVerificationSheet(p);   // credentialOptions, otpRequired, verificationStatus
      if (form == null) return onSend('cancel', payload: {'confirm': false});
      await onSend('Verify', payload: {
        if (form.otp != null) 'otp': form.otp,
        if (form.pin != null) 'pin': form.pin,
        if (form.password != null) 'password': form.password,
      });
    case 'APP_ACTION':
      final ui = (p['ui'] as Map).cast<String, dynamic>();
      final route = ui['route'] as String?;
      final canOpen = ui['kind'] == 'screen' && isOpenableRoute(route);
      showAppActionCard(title: ui['title'], needs: ui['needs'],
          onOpen: canOpen ? () => Get.toNamed(route!, arguments: ui['prefill']) : null);
    case 'SERVICE_UNAVAILABLE':
      showRetry(() => onSend(message, payload: payload, category: category, service: service));
    case 'AUTH_REQUIRED':
      await refreshLogin();
      showRetry(() => onSend(message, payload: payload, category: category, service: service));
    case 'BANKING_SERVICE':
      renderServiceCard(turn);   // per-intent rendering, see each handoff
    default:
      break;                     // bubble text is the whole answer
  }
}
```

Don't offer Retry for answers to an open question (Yes/No, a pick, the verification form).
They only mean something while that question is open, and verification values must not be kept
for a resend.

## 11. UI to build — building blocks, and the table in each intent file

Every intent file has a table **"UI to build, use case by use case"**: one row per use case, saying which
block to show, which buttons, what is prefilled, and which bank call the app makes. The blocks are defined here once.
Decide everything from `result.type`, `category`, `service`, `routing` and `payload` — never from the bubble text.

**The rule: the customer finishes everything inside the chat.** Follow the nickname and email change: a box
in the chat, prefilled from what the customer already said, with buttons. Redirecting to another screen is
not the plan; `ui.route` is only an optional fallback for a box that has not been built yet.

| Block | Shown when | Contents | Buttons |
|---|---|---|---|
| **U1 Text bubble** | Always | The streamed reply. Wording varies every time. | — |
| **U2 List card** | A lookup returns a list (loans, disputes, requests, gifts...) | Title and count; one row per item (title, subtitle, value or status), using the fields documented under "Response — `result.payload`" in the intent file. An empty list shows the bubble only. | None unless the table says otherwise |
| **U3 Detail card** | A lookup returns one record (balance, profile, address, credit card summary...) | Label / value pairs with the main value prominent. Mask numbers as given. | — |
| **U4 Transaction list** | Transaction history, account transactions | Rows: date, description, amount, direction. **Amounts in these payloads are poisha: divide by 100.** | — |
| **U5 Picker** | `ACCOUNT_SELECTION_REQUIRED`, `TRANSACTION_SELECTION_REQUIRED`, `BENEFICIARY_SELECTION_REQUIRED` | One tappable row per candidate | A tap sends the pick (see §6) |
| **U6 Confirm card** | `CONFIRMATION_REQUIRED` | The values that will change (from `payload`) | **Yes** / **No** → message `Yes`/`No` + `{"confirm": true}` or `{"confirm": false}` |
| **U7 Verification sheet** | `OTP_REQUIRED`, and the code/PIN step of an inline box | Where the code was sent; code field; PIN or password field only when the table says so | **Verify**, **Cancel** |
| **U8 Inline action box** | `APP_ACTION` with a card in the table, and every gather-and-redirect summary (transfers, dispute, lost card, photo) | A card inside the chat with the fields of the real screen, **prefilled** from `ui.prefill` (or `payload` for the gather summaries). Fields the customer did not give are empty or have a picker the app fills from its own data (accounts, cards, beneficiaries, requests). | The box's own buttons (named per use case). Then U7 when the table says a code or PIN is needed, then a local done or failed tile. |
| **U9 Info card** | `APP_ACTION` with `ui.kind` `info` or `unavailable`, or when no app path exists | `ui.title` and the bubble. No button. | — |
| **U10 Retry bar** | `SERVICE_UNAVAILABLE`, `AUTH_REQUIRED` | Short notice | **Retry** (resend the last message); on `AUTH_REQUIRED` refresh the login first |
| **U11 Fallback button** (optional) | A box that is not built yet and `ui.route` is a plain, openable path | `ui.title` | **Open** → `Get.toNamed(ui.route, arguments: ui.prefill)`. Never the primary design. |

The app chooses the box by `result.service` (the action id, stable). For gather-and-redirect results it uses
`category`/`service`/`subservice` and `payload`. The **boxes call the app's existing use cases** (the same code as the
full screens) so the one-time code, PIN and limit checks are identical; the bot never makes these bank calls, and is not
told the outcome. For code or PIN steps reuse the verification sheet the app already has for card freeze and email change.

### What the backend does NOT provide yet

1. **Showing the complaint or dispute box at the right moment (built).** Every missing-field `CLARIFICATION_REQUIRED` now carries `payload.pending = {"category", "service", "subservice", "missingFields": [...]}` (field names only, never values). Show the complaint box when `pending.service == "submit_complaint"` (missing `description`) and the dispute box when `pending.service == "raise_dispute"` (missing `remarks`). When `payload` is `null` (a plain question) or `pending` is absent, show nothing extra: the customer just types. The box sends a direct request: `support`/`submit_complaint` with `{"description", "category"}`, or `service_requests`/`raise_dispute` with `{"remarks"}`; the bot answers with the Yes/No card or the dispute summary.
2. **The result of an inline action.** The app does not tell the bot whether a box succeeded, so the bot's next reply does not mention it. If that is wanted, the app can send a short message after success (for example "Done"); nothing in the backend needs to change for that.
