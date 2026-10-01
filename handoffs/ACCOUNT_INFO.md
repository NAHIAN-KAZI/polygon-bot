# ACCOUNT_INFO — Integration Handoff

Covers the bank's ACCOUNT_INFO intent plus a few real, closely-related
account features that live under the same `account_info` wire category.
Base connection details (URL, auth header, SSE event shapes) are in the main
`HANDOFF.md`/`INTEGRATION.md` — this doc only covers what's specific here.

**Important mapping note**: our `account_info` wire category does not map
1:1 onto the bank's own ACCOUNT_INFO intent numbering. Some services here
(`balance`, `device_history`, `login_history`) technically belong to other
bank intents (CHECK_BALANCE; "Authentication and Security," not any of the
14). One service (`my_loans`, ACCOUNT_INFO 1.6) is served under a
**different** wire category, `loan_services`, because that's where the
bank's own live taxonomy actually puts it. Route by `category`+`service`,
not by which bank intent a feature conceptually belongs to.

## Services in this doc

| Service | Wire category/service | Status |
|---|---|---|
| Balance | `account_info` / `balance` | ✅ Real |
| List/detail accounts | `account_info` / `accounts` | ✅ Real |
| Device history | `account_info` / `device_history` | ✅ Real |
| Login history | `account_info` / `login_history` | ✅ Real |
| Cards list | `account_info` / `cards` | ✅ Real (new, T-57) |
| My loans | `loan_services` / `my_loans` | ✅ Real (new, T-58) |
| FD profit history | `account_info` / `fd_profit_history` | ✅ Real (new, T-58) |
| DPS profit history | `account_info` / `dps_profit_history` | ✅ Real (new, T-58) |

Deliberately **not implemented** (user-confirmed, not real chatbot asks):
account-by-number lookup (1.3) and account-by-username lookup (1.4) — both
are internal signup/device-verification flows in the real app, not things
an authenticated customer naturally asks their chatbot.

## How to trigger each one

Natural language, or direct route (`category`/`service`/`payload`, bypasses
classification):

- **Balance**: "what's my balance?" → `{"category":"account_info","service":"balance"}`
- **Accounts**: "how many accounts do i have?" → `{"category":"account_info","service":"accounts"}`
- **Device history**: "what devices are logged in?" → `{"category":"account_info","service":"device_history"}`
- **Login history**: "show my login history" → `{"category":"account_info","service":"login_history","payload":{"deviceId":"<id>"}}` (`deviceId` **required** — see below)
- **Cards**: "show my cards" → `{"category":"account_info","service":"cards"}`
- **My loans**: "show my loans" / "my loan status" → `{"category":"loan_services","service":"my_loans"}`
- **FD profit history**: "show my FD profit history" → `{"category":"account_info","service":"fd_profit_history"}`
- **DPS profit history**: "show my DPS profit history" → `{"category":"account_info","service":"dps_profit_history"}`

## Request payload

| Service | Field | Required | Notes |
|---|---|---|---|
| `accounts` | `id` | No | Omit for the full list; pass to get one account's detail |
| `login_history` | `deviceId` | **Yes** | From a prior `device_history` call |
| `login_history` | `startDate`/`endDate` | No | ISO dates, filters the range |
| `fd_profit_history` | `id` | No | Auto-resolved if the customer has exactly 1 FD account; if 2+, triggers `ACCOUNT_SELECTION_REQUIRED` |
| `dps_profit_history` | `id` | No | Same auto-resolve pattern, for DPS |
| `balance`, `cards`, `my_loans` | — | — | No payload needed |

## Response — `result` event (real examples, live-captured 2026-10-01)

**Balance**:
```json
{"type": "BANKING_SERVICE", "category": "account_info", "service": "balance",
 "payload": {"balance": 100228201915, "balanceFormatted": "৳100,228,201,915"}}
```
`balance` is a raw integer (poisha-scale as returned by the bank); `balanceFormatted` is ready-to-display BDT.

**Cards** (`{"cards": [...]}`, each entry from the account's own `cards[]` array — already masked by the bank, e.g. `"4001****0251"`):
```json
{"type": "BANKING_SERVICE", "category": "account_info", "service": "cards",
 "payload": {"cards": [
   {"cardNumber": "4001****0251", "cardType": "DEBIT", "formFactor": "PHYSICAL",
    "holderName": "Ahad Shikder", "id": "41", "linkedAccountNumber": "100126000015",
    "starred": false, "status": "ACTIVE"}
 ]}}
```

**My loans** (`{"loans": [...]}`, empty array if none):
```json
{"type": "BANKING_SERVICE", "category": "loan_services", "service": "my_loans",
 "payload": {"loans": []}}
```

**DPS profit history** (`{"profitHistory": [...]}`, empty array if no history yet):
```json
{"type": "BANKING_SERVICE", "category": "account_info", "service": "dps_profit_history",
 "payload": {"profitHistory": []}}
```

**FD profit history — known gap, not a bug**: this service classifies and
routes correctly, but the bank's own `product/v1/fixed-deposit/{id}/profit-history`
endpoint currently 404s for at least one real, active FD account in our test
environment (confirmed independently via raw curl with both the account's
`identifier` and its numeric internal `id` — both 404 "Fixed Deposit not
found"). This is a platform-side data gap, not a code issue. Per explicit
user decision, this surfaces as a plain `SERVICE_UNAVAILABLE`, not a
special "no FD account" message — treat it exactly like any other
`SERVICE_UNAVAILABLE`:
```json
{"type": "SERVICE_UNAVAILABLE", "category": "account_info", "service": "fd_profit_history"}
```

**Multi-account selection** (FD/DPS profit history, when the customer has
2+ accounts of that type):
```json
{"type": "ACCOUNT_SELECTION_REQUIRED", "category": "account_info", "service": "fd_profit_history",
 "payload": {"accounts": [{"identifier": "FDDE1F32376C574CB9", "chartOfAccountName": "Fixed Deposit"}, ...]}}
```
Resubmit with `payload.id` set to the chosen `identifier`.

## Frontend integration (Dart)

SSE handling — this backend has no code-side SSE client dependency, just
raw `event:`/`data:` lines over a chunked HTTP response. Minimal manual
parser using the `http` package:

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

Future<void> streamChat(String message, String jwt) async {
  final request = http.Request('POST', Uri.parse('$baseUrl/chat'))
    ..headers['Content-Type'] = 'application/json'
    ..headers['X-API-Key'] = apiKey
    ..headers['Authorization'] = 'Bearer $jwt'
    ..body = jsonEncode({'message': message});

  final response = await http.Client().send(request);
  String? currentEvent;
  await for (final line in response.stream
      .transform(utf8.decoder)
      .transform(const LineSplitter())) {
    if (line.startsWith('event: ')) {
      currentEvent = line.substring(7).trim();
    } else if (line.startsWith('data: ')) {
      final data = jsonDecode(line.substring(6));
      switch (currentEvent) {
        case 'token':
          appendToChatBubble(data['token'] as String);
          break;
        case 'result':
          handleResult(data as Map<String, dynamic>);
          break;
        case 'done':
          finishTurn();
          break;
      }
    }
  }
}

void handleResult(Map<String, dynamic> result) {
  switch (result['type']) {
    case 'BANKING_SERVICE':
      _renderAccountInfoCard(result['service'] as String, result['payload']);
      break;
    case 'ACCOUNT_SELECTION_REQUIRED':
      _renderAccountPicker((result['payload']['accounts'] as List)
          .cast<Map<String, dynamic>>());
      break;
    case 'SERVICE_UNAVAILABLE':
      // same generic handling as every other intent — no special case
      break;
  }
}

void _renderAccountInfoCard(String service, Map<String, dynamic> payload) {
  switch (service) {
    case 'balance':
      // single stat tile: payload['balanceFormatted']
      break;
    case 'cards':
      // list of card tiles from payload['cards'] — each already has a
      // masked cardNumber, render as-is, never unmask
      break;
    case 'my_loans':
      // list from payload['loans'], or an empty-state if []
      break;
    case 'dps_profit_history':
    case 'fd_profit_history':
      // list from payload['profitHistory'], or an empty-state if []
      break;
  }
}
```

**Rendering recommendations**:
- Balance → a single stat tile, use `balanceFormatted` directly, never the raw integer.
- Cards → a list of card tiles (icon by `cardType`, show `formFactor`); `cardNumber` is already masked by the bank, display as-is.
- Accounts → reuse whatever table/card layout you already built for the existing `accounts` service (unchanged this session).
- My loans / FD/DPS profit history → a simple list, with a clear empty-state ("No active loans"/"No profit history yet") when the array is `[]` — don't treat an empty array as an error.
- `ACCOUNT_SELECTION_REQUIRED` for FD/DPS → a simple picker list using `chartOfAccountName` as the label, resubmitting with `payload.id`.

**Action buttons**: none needed for any service in this doc — all purely informational, `routing.action` is always the generic `"redirect"` value.

## Live-verified (2026-10-01)

- "what's my balance?" → real balance, correct formatting.
- "how many accounts do i have?" → real account list, 5 ledger accounts (Customer ×2, Fixed Deposit, DPS Deposit, Credit Card Receivable).
- "show my loans" / "my loan status" → both correctly resolve to `loan_services`/`my_loans`, real empty-loans response.
- "show my DPS profit history" → auto-resolved the customer's single DPS account, real empty-history response.
- "show my FD profit history" → correctly classifies/routes, hits the documented platform-side 404 (expected, not a bug).
- Cards list → live-verified directly against the adapter, 4 real cards returned (1 physical, 3 virtual).
- Multi-account-selection reply text verified distinguishable for FD/DPS (fixed a bug where it rendered blank for 2+ matches — see TASKS.md T-58).

## Known gaps

1. FD profit history's platform-side 404 (above) — left as `SERVICE_UNAVAILABLE` by explicit user decision, not fixed further on our end.
2. Account-by-number (1.3) and account-by-username (1.4) deliberately not implemented — not real chatbot use cases.
3. The "genuine answering" case for `ACCOUNT_SELECTION_REQUIRED` (customer replies "the savings account" instead of picking from the list) doesn't yet resolve to a specific account — a separate, pre-existing gap (found during T-59), needs the full account list (not just masked numbers) persisted in session state plus type/last-4-based resolution. Not yet scheduled.
