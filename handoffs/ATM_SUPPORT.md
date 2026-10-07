# ATM_SUPPORT — Integration Handoff

ATM problems (card charged, no cash), dispute status, and cash-by-code.
Read `COMMON.md` first; the dispute gathering is detailed in `FAILED_TRANSFER.md`.

## Services

| Ask | `category` / `service` | Status |
|---|---|---|
| Cash by code (2.1) | `app_actions` / `cash_by_code` | ✅ App action (`APP_ACTION`, no bank call) |
| Raise dispute (2.2) | `service_requests` / `raise_dispute` | ✅ Gather + redirect (never submits) |
| List disputes (2.3) | `service_requests` / `disputes` (`GET service-request/v1/disputes`) | ✅ Live |

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 2.1 | Cash by code | App action `cash_by_code` → `CashByCodeScreen`, `/cash_by_code` (Open). Prefill: `amount` (taka), `recipientMobile` |
| 2.2 | Raise dispute | Gather + redirect: `service_requests` / `raise_dispute`, `routing.action: "raise_dispute"` (never submitted by the bot) |
| 2.3 | List disputes | Handled in chat: `service_requests` / `disputes` |

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 2.1 | Cash by code | App action → inline box | **U8** box: Form: account to send from, recipient mobile, amount, how the code is delivered (screen, SMS or email), note. After the button: U7: code + transaction PIN. | Send | `amount`, `recipientMobile` (from `ui.prefill`) | App calls `POST transfer/v1/cash-by-code`; shows a local done/failed tile |
| 2.2 | Raise dispute | Gather → inline box | U5 account and transaction pickers when needed → **U8** dispute box: account and transaction (prefilled), category, reason text | Submit dispute | `accountNumber`, `transactionReferenceNo`, `remarks` | U7: code · `POST service-request/v1/disputes` |
| 2.3 | List disputes | Answered in chat | **U2 disputes** — Dispute rows: reference, status, date. | None | None | — |

<!-- UI-TO-BUILD:END -->

## How to trigger

Live-tested:
- "ATM took my card money but no cash came out" → `raise_dispute` gathering.
- "any open disputes", "status of my dispute" → `disputes`.
- "can i withdraw 500 taka using rocket via code" → `APP_ACTION` `cash_by_code` (live run 2026-10-06). Short asks ("Withdraw cash") may get a clarifying question first.

Direct route: `{"message": "show", "category": "service_requests", "service": "disputes"}`.

## Response — `result.payload`

**disputes** (live): `{"disputes": []}` — empty is the normal "none" answer.

**raise_dispute** summary: see `FAILED_TRANSFER.md` (`accountNumber`,
`transactionReferenceNo`, `remarks`, `executed: false`, `routing.action: "raise_dispute"`).

**cash by code**: `APP_ACTION` (see `COMMON.md` §8; illustrative):
```json
{"type": "APP_ACTION", "category": "app_actions", "service": "cash_by_code",
 "payload": {"ui": {"kind": "screen", "title": "Cash by code", "screen": "CashByCodeScreen",
   "route": "/cash_by_code", "prefill": {"amount": 500}, "needs": "..."}, "executed": false},
 "routing": {"category": "app_actions", "service": "cash_by_code", "subservice": null, "action": "cash_by_code"}}
```
`prefill` holds only what the customer wrote (here an amount), or is `null`.

A dispute's account and transaction are looked up first: several accounts →
`ACCOUNT_SELECTION_REQUIRED`; no clear transaction match → `TRANSACTION_SELECTION_REQUIRED`
(see `COMMON.md` §6 and `FAILED_TRANSFER.md`).

## Frontend integration (Dart)

```dart
void renderAtmSupport(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'disputes':
      final items = (p['disputes'] as List);
      if (items.isNotEmpty) showDisputeList(items.cast<Map<String, dynamic>>());
    case 'raise_dispute':
      showDisputeSummaryCard(p, onContinue: () => openAppScreen('raise_dispute', prefill: p));
  }
}
```

Rendering: dispute list as status rows. Cash by code is the shared `APP_ACTION`
card with an **Open** button (`Get.toNamed('/cash_by_code', arguments: prefill)`).

## Live-verified (`taslim_islamic`)

The dispute triggers above on 2026-10-03; cash by code on 2026-10-06.

## Known gaps

1. Non-empty dispute entries not seen live — confirm fields before finalising rows.
