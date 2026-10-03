# ACCOUNT_INFO — Integration Handoff

The customer's accounts, cards, devices and logins, loans and FD/DPS profit.
Read `COMMON.md` first (Dart client, result types, selection, money units).

## Services

| Ask | `category` / `service` | Status |
|---|---|---|
| List/count accounts | `account_info` / `accounts` | ✅ Live |
| Cards list | `account_info` / `cards` | ✅ Live |
| Enrolled devices | `account_info` / `device_history` | ✅ Live |
| Login history | `account_info` / `login_history` | ✅ Live (all devices; no device id needed) |
| My loans | `loan_services` / `my_loans` | ✅ Live |
| FD profit history | `account_info` / `fd_profit_history` | ✅ Built (see gaps) |
| DPS profit history | `account_info` / `dps_profit_history` | ✅ Built (see gaps) |
| One account's transactions | `account_info` / `account_transactions` | ✅ Live (direct route only; chat uses MINI_STATEMENT's `transaction_history`) |

Not implemented on purpose: account by number (1.3) and by username (1.4) —
pre-login signup/device-verification steps, not chat asks. Starring an
account (1.5) changes data and is blocked; the bot says it's done in the app.

## How to trigger

Any wording works — one word, typos, Banglish, long paragraphs. Live-tested:

- accounts: "accounts", "amar koyta account ase", "Could you kindly list all the accounts I hold…"
- cards: "cards", "my crads"
- devices: "devices"; logins: "where was my account logged in from recently?"
- loans: "loans", "amar kono loan ache?"
- DPS/FD: "dps", "how much profit did my dps make", "fd profit"

Direct route: `{"message": "show", "category": "account_info", "service": "accounts"}`.

## Request payload

| Service | Field | Required | Notes |
|---|---|---|---|
| `accounts` | `id` | — | One account's detail; omit for all |
| `login_history` | `deviceId` | — | Omit for recent logins across all enrolled devices (newest first, max 20). Pass a `deviceId` from `device_history` for one device |
| `login_history` | `startDate`, `endDate` | — | `yyyy-MM-dd`, inclusive |
| `fd_profit_history`, `dps_profit_history` | `identifier` | — | Auto-picked with one FD/DPS; several → `ACCOUNT_SELECTION_REQUIRED` (ledger shape) |
| `account_transactions` | `id` / `accountNumber` | — | Auto-picked with one account; several → selection |

## Response — `result.payload` (live, 2026-10-03)

**accounts** — passed through from the bank. Each account appears under both
`accounts` (core record) and `ledgerAccounts` (accounting ledger, matched by
`identifier == accountNumber`). **Show the ledger balance**
(`ledgerAccounts[].balanceFormatted`); the core record's `balance` was `"0.00"`
while the real balance was Tk 90,000. The bot's own reply already does this.

```json
{"data": {
  "accounts": [{"accountName": "taslim_islamic", "accountNumber": "100126000056",
    "accountType": "SAVINGS", "balance": "0.00", "bankingMode": "ISLAMIC",
    "branchName": "banani", "accountNumberMasked": "••••••••0056",
    "cards": [{"cardNumber": "4001****0293", "cardType": "DEBIT", "id": "45", "status": "ACTIVE"}]}],
  "ledgerAccounts": [{"identifier": "100126000056", "identifierMasked": "••••••••0056",
    "balance": "9000000", "balanceFormatted": "৳90,000.00",
    "chartOfAccountName": "Customer", "name": "taslim_islamic", "status": "FULL_ACTIVE"}]}}
```

**cards** — card numbers are already masked by the bank:
```json
{"cards": [{"id": "45", "cardNumber": "4001****0293", "cardType": "DEBIT",
  "formFactor": "PHYSICAL", "holderName": "taslim_islamic",
  "linkedAccountNumber": "100126000056", "starred": false, "status": "ACTIVE"}]}
```

**device_history**:
```json
{"devices": [{"id": 161, "deviceId": "76c16c79…", "deviceName": "motorola motorola edge 60 fusion",
  "platform": "ANDROID", "biometricEnabled": false,
  "enrolledAt": "2026-09-29T15:36:52+06:00", "lastUsedAt": "2026-10-01T18:06:46+06:00",
  "lastKnownIp": "10.42.6.247"}]}
```

**login_history** (no `deviceId` sent):
```json
{"records": [{"loginAt": "2026-10-01T18:06:46+06:00", "status": "SUCCESS",
  "deviceName": "motorola motorola edge 60 fusion", "ipAddress": "10.42.6.247",
  "platform": "ANDROID", "riskLevel": "NORMAL", "newDevice": false, "newIp": false}],
 "devicesChecked": 2}
```

**my_loans**: `{"loans": []}` — empty list = no loans (normal, not an error).

**account_transactions** (amounts in poisha):
```json
{"data": {"transactions": [{"id": "5354", "date": "29-09-2026 16:05", "type": "DEBIT",
  "amount": "500000", "description": "bKash: From 100126000056 to 10002030"}]}, "status": "success"}
```

## Frontend integration (Dart)

```dart
void renderAccountInfo(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'accounts':
      final data = (p['data'] as Map).cast<String, dynamic>();
      final ledgers = {
        for (final l in (data['ledgerAccounts'] as List? ?? const []))
          l['identifier']: l
      };
      final rows = [
        for (final a in (data['accounts'] as List))
          AccountRow(
            name: a['accountName'],
            type: a['accountType'],
            numberMasked: a['accountNumberMasked'] ?? mask(a['accountNumber']),
            // ledger balance is the real one
            balance: ledgers[a['accountNumber']]?['balanceFormatted'],
          )
      ];
      showAccountCards(rows);
    case 'cards':
      showCardTiles((p['cards'] as List).cast<Map<String, dynamic>>());
    case 'device_history':
      showDeviceList((p['devices'] as List).cast<Map<String, dynamic>>());
    case 'login_history':
      showLoginTimeline((p['records'] as List).cast<Map<String, dynamic>>());
    case 'my_loans':
      final loans = (p['loans'] as List);
      loans.isEmpty ? showEmpty('No loans') : showLoanList(loans);
    case 'account_transactions':
      showTransactions(((p['data'] as Map)['transactions'] as List),
          amount: (t) => Money.fromPoisha(int.parse(t['amount'])));
  }
}
```

Rendering: accounts and cards as cards (few items, key facts); devices and
logins as a list/timeline; empty lists as a one-line empty state — the bubble
text already says "none". Action buttons: optional "Open in app" per item;
nothing here changes data.

FD/DPS `SERVICE_UNAVAILABLE` is the normal answer for a customer whose FD/DPS
record the bank can't return (see gaps) — show the bubble only.

## Live-verified (2026-10-03, dev user `taslim_islamic`)

- "accounts" / "amar koyta account ase" / formal paragraph → `accounts`, reply "one savings account … Tk 90,000.00".
- "cards", "my crads" → `cards`, card ending 0293.
- "devices" → 2 devices; "Hi, I got a weird notification yesterday. Can you show me where my account was logged in from recently?" → `login_history`, 3 real logins across both devices.
- "loans", "amar kono loan ache?" → `my_loans`, "no loans".

## Known gaps

1. FD/DPS profit history: the bank returns 404 for this test customer's records → `SERVICE_UNAVAILABLE` (kept as-is by decision). Not re-verified on a customer with a real FD/DPS.
2. "how mny acount i hav" (heavy typo) is sometimes read as a balance ask; the reply still states the single account and its balance.
3. Multi-account selection is unit-tested; the dev user has one account, so it isn't live-verified.
