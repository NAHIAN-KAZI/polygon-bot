# Common — Chat API contract and shared Dart client

Every per-intent handoff in this folder builds on this page: one Dart client,
one result envelope, and the generic result types every intent can return.
Connection details (base URL, API key) are in `INTEGRATION.md`.

## 1. Request

`POST /chat`, headers `X-API-Key: <key>`, `Content-Type: application/json`,
and `Authorization: Bearer <customer JWT>` for anything account-related.

| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | string | ✅ | 1–4000 chars, what the customer typed (or a short label like `"Selected"` when the app sends a structured answer) |
| `category`, `service`, `subservice` | string | — | Pass `category`+`service` together to skip understanding and call one service directly (ids exactly as in each intent doc) |
| `payload` | object | — | Structured answers: a picked account/card, the OTP form, or direct-route fields |

The customer's identity always comes from the JWT. The bot keeps a short
per-customer conversation, so a follow-up ("the savings one", "500",
"yes") is understood in context — the app just sends the next message.

## 2. Response stream (SSE)

`text/event-stream`, in this order:

1. `event: token` — `{"token": "..."}`, one or more. Concatenate them: this is the
   chat bubble text (English, already worded for the customer).
2. `event: result` — exactly one, the structured outcome (below).
3. `event: done` — `{}`. Close the stream.

`event: error` (`{"detail": "..."}`) can replace 1–2 if something failed
server-side; show a generic "something went wrong, please try again".

## 3. `result` envelope

```json
{"type": "BANKING_SERVICE", "category": "account_info", "service": "balance",
 "subservice": null, "payload": {...}, "routing": {...} | null, "version": "1.0"}
```

| `type` | Meaning | What the app should do |
|---|---|---|
| `BANKING_SERVICE` | A service answered (data) or a gather-only flow finished (summary) | Show the bubble; optionally render `payload` as a card/table (each intent doc says how) |
| `CLARIFICATION_REQUIRED` | The bot asked a question | Show the bubble; keep the input open. `payload` is `null` |
| `ACCOUNT_SELECTION_REQUIRED` | The customer has several accounts/cards and the bot asked which | Show the bubble **and** a picker from `payload.accounts` (§4) |
| `OTP_REQUIRED` | Card freeze needs verification | Open the secure verification form (§5). Never collect codes in the chat box |
| `TRANSACTION_SELECTION_REQUIRED` | A dispute needs to know which recent transaction it's about | Show the bubble **and** a picker from `payload.transactions` (`transactionId`, `txnTime`, `type`, `amount`, `transactionType`); send the pick as `payload: {"transactionId": id}` |
| `CONFIRMATION_REQUIRED` | A change is ready and needs an explicit yes/no | Show the bubble plus **Yes** / **No** buttons that send `payload: {"confirm": true}` / `{"confirm": false}` (message text can be the button label). Typed replies also work — the bot reads them — but buttons are exact |
| `SERVICE_UNAVAILABLE` | The bank's service failed or isn't available for this customer | Show the bubble; optionally a retry button that resends the last message |
| `AUTH_REQUIRED` | JWT missing/expired | Refresh the token (or send the customer to login), then resend |
| `KB_ANSWER` | General/product answer from the bank's knowledge base, or a polite off-topic decline | Show the bubble. `payload.sources` lists documents used (may be `null`) |
| `UNKNOWN_SERVICE` | Recognised as banking but not something chat can do | Show the bubble |
| `BENEFICIARY_MATCH` | "Send money to <name>" matched one saved beneficiary | Beneficiary card + "Send" button to the transfer screen (see `TRANSFER.md`) |
| `BENEFICIARY_SELECTION_REQUIRED` | Several beneficiaries match the name | Picker; send `payload: {"beneficiaryId": id}` (see `TRANSFER.md`) |

`routing.action` (when present) names the app screen the request belongs to
(e.g. `bkash_transfer`, `other_bank_transfer`, `raise_dispute`, `redirect`).
Use it for an optional "Open in app" button; the chatbot never executes
transfers or disputes itself.

## 4. Account / card selection

```json
{"type": "ACCOUNT_SELECTION_REQUIRED", "category": "account_info", "service": "balance",
 "payload": {"accounts": [
   {"accountNumber": "100126000015", "accountName": "Ahad", "accountType": "SAVINGS"},
   {"accountNumber": "4100200000000379", "accountName": "Ahad", "accountType": "CREDIT"}]}}
```

Card lists carry `{"id", "cardNumber" (masked), "cardType"}` instead; ledger
accounts (FD/DPS) carry `{"identifier", "chartOfAccountName"}`. The customer can
answer in words ("the savings one", "ending 0015") **or** the app can send the
pick directly — the original request then resumes automatically:

```dart
// Picker tap: send the chosen entry's id field back.
sendMessage('Selected', payload: {'accountNumber': picked['accountNumber']});
// cards:  payload: {'cardId': picked['id']}
// ledger: payload: {'identifier': picked['identifier']}
```

Display only the last 4 digits; the full numbers are for the resubmit.

## 5. Secure verification (card freeze only)

`OTP_REQUIRED` means an SMS code was sent to the customer's registered phone.
Show a form with **OTP** plus **either** card PIN **or** login password
(`payload.credentialOptions`). Submit it as a structured payload — never as
chat text, never logged by the app:

```dart
sendMessage('Verify', payload: {'otp': otp, 'pin': pin});      // or 'password': pwd
```

`payload.verificationStatus` tells the form what happened:
`OTP_SENT`, `OTP_RESENT`, `CREDENTIALS_MISSING`, `CREDENTIALS_INVALID_COMBINATION`
(sent both PIN and password), `OTP_INCORRECT` (`attemptsRemaining` included),
`OTP_EXPIRED` (a new code was sent), `OTP_BLOCKED`, `SEND_THROTTLED`.
A plain chat message instead of the form (e.g. "what's my balance") leaves the
freeze step; "cancel" cancels it.

## 6. Money, numbers, privacy

- Bank amounts in `payload` are **poisha** (1 Tk = 100 poisha), exactly as the bank
  returns them — use your existing `Money.fromPoisha`. Exception: QR payment
  history is already taka. Fields ending in `Formatted` are ready-to-show taka.
- Amounts the **customer** typed (transfer/fee summaries) are taka.
- The bubble text never contains a full account or card number; `payload` may
  (it is the customer's own data, for the app's own rendering) — mask on screen.

## 7. Dart client (shared by every intent doc)

Uses `package:http` streaming and manual SSE parsing.

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class ChatTurnResult {
  final String text;                       // concatenated `token` events
  final Map<String, dynamic>? result;      // the `result` event
  ChatTurnResult(this.text, this.result);
  String? get type => result?['type'] as String?;
  String? get category => result?['category'] as String?;
  String? get service => result?['service'] as String?;
  Map<String, dynamic>? get payload =>
      (result?['payload'] as Map?)?.cast<String, dynamic>();
}

class PolygonBotClient {
  PolygonBotClient(this.baseUrl, this.apiKey, this.jwtProvider);
  final String baseUrl;
  final String apiKey;
  final Future<String?> Function() jwtProvider;

  Future<ChatTurnResult> send(String message,
      {Map<String, dynamic>? payload, String? category, String? service,
       void Function(String partial)? onToken}) async {
    final req = http.Request('POST', Uri.parse('$baseUrl/chat'))
      ..headers.addAll({
        'X-API-Key': apiKey,
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        if (await jwtProvider() case final jwt?) 'Authorization': 'Bearer $jwt',
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
          throw Exception(data['detail']);
        }
      }
    }
    return ChatTurnResult(text.toString(), result);
  }
}
```

Typical dispatch in the chat screen (each intent doc adds its own `case`):

```dart
Future<void> onSend(String message, {Map<String, dynamic>? payload}) async {
  final turn = await bot.send(message, payload: payload,
      onToken: (partial) => showTypingBubble(partial));
  showBotBubble(turn.text);
  switch (turn.type) {
    case 'ACCOUNT_SELECTION_REQUIRED':
      showPicker((turn.payload!['accounts'] as List).cast<Map<String, dynamic>>());
    case 'OTP_REQUIRED':
      showVerificationForm(turn.payload!);
    case 'CONFIRMATION_REQUIRED':
      showYesNo(onYes: () => onSend('Yes', payload: {'confirm': true}),
                onNo: () => onSend('No', payload: {'confirm': false}));
    case 'TRANSACTION_SELECTION_REQUIRED':
      showTransactionPicker((turn.payload!['transactions'] as List).cast<Map<String, dynamic>>(),
          onPick: (t) => onSend('Selected', payload: {'transactionId': t['transactionId']}));
    case 'AUTH_REQUIRED':
      await refreshLogin();
    case 'BANKING_SERVICE':
      renderServiceCard(turn);   // per-intent rendering, see each handoff
    default:
      break;                     // bubble text is the whole answer
  }
}
```

## 8. Bot wording (T-77)
Every bubble is written by the model for this customer and moment, so the same
step can be worded differently each time. Never match on bubble text; drive the
UI only from `result.type`, `payload` and `routing`. Only one sentence is fixed:
when the bot's language model can't be reached it says
"Sorry, I'm having trouble right now. Please try again in a moment."
