# CARD_ISSUE — Integration Handoff

A card problem: viewing complaints/tickets and disputes, raising a dispute
(gathered in chat, submitted in the app), submitting a complaint (in chat, after a yes),
and steering vague problems.
Read `COMMON.md` first; raising a dispute is detailed in `FAILED_TRANSFER.md`.

## Services

| Ask | `category` / `service` | Status |
|---|---|---|
| My complaints / tickets (3.6) | `polygon_services` / `my_tickets` (`GET support/v1/complaints`) | ✅ Live |
| List disputes (3.4) | `service_requests` / `disputes` | ✅ Live |
| Raise dispute (3.3) | `service_requests` / `raise_dispute` | ✅ Gather + redirect (never submits) |
| Submit complaint (3.5) | `support` / `submit_complaint` (`POST support/v1/complaints`) | ✅ In chat after an explicit yes (approved change) |
| Reset PIN (3.1), unfreeze (3.2) | `app_actions` / `card_pin_reset`, `card_unfreeze` | ✅ App action (`APP_ACTION`, no bank call) |

"My Tickets" in the app = `GET support/v1/complaints` (confirmed by the bank
team); there is no separate ticket API.

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 3.1 | Reset card PIN | App action `card_pin_reset` → `SelectCardForPinResetScreen`, `/set_reset_card_pin` (Open). Prefill: `cardLast4` |
| 3.2 | Unfreeze card | App action `card_unfreeze` → `FreezeCardScreen`, `/freeze_card` (Open). Prefill: `cardLast4` |
| 3.3 | Raise dispute | Gather + redirect: `service_requests` / `raise_dispute`, `routing.action: "raise_dispute"` |
| 3.4 | List disputes | Handled in chat: `service_requests` / `disputes` |
| 3.5 | Submit complaint | Executed in chat after yes/no: `support` / `submit_complaint` (`CONFIRMATION_REQUIRED` → Yes → `BANKING_SERVICE`, `executed: true`) |
| 3.6 | My complaints | Handled in chat: `polygon_services` / `my_tickets` |

## How the bot handles card problems

- "my card isnt working" → a question about what's happening (never a freeze); it may offer concrete options in the text.
- Lost/stolen/misused → report-lost redirect, or the freeze flow when the customer asks to freeze/block (`LOST_OR_STOLEN_CARD.md`).
- "file a complaint about …" → `submit_complaint`: the bot asks what it's about if needed, then a yes/no with the complaint `category` and `description` (`COMMON.md` §7).
- "reset my pin", "unfreeze my card" → `APP_ACTION`.
- "show my complaints", "any update on my tickets?" → `my_tickets`.
- "status of my dispute", "any open disputes" → `disputes`.
- A charge/transaction problem → `raise_dispute` gathering.

## Response — `result.payload` (live)

**my_tickets**: `{"complaints": []}` · **disputes**: `{"disputes": []}`.
Empty = none (normal answer).

**submit_complaint** yes/no step:
```json
{"type": "CONFIRMATION_REQUIRED", "category": "support", "service": "submit_complaint",
 "payload": {"category": "MOBILE_APP_TECHNICAL", "description": "The app hangs when I pay a bill"}}
```
Yes → `BANKING_SERVICE` with the bank's response plus `executed: true` (it then shows under
My Tickets). No → `{"executed": false, "cancelled": true}`.

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 3.1 | Reset card PIN | App action → inline box | **U8** box: Card (preselected from `cardLast4`, else the card picker) with a **Reset PIN** button. After the button: U7: code + PIN or password. | Reset PIN | `cardLast4` (from `ui.prefill`) | App calls `PATCH card/v1/cards/{id}/reset-pin`; shows a local done/failed tile |
| 3.2 | Unfreeze card | App action → inline box | **U8** box: Frozen cards (preselected from `cardLast4`) each with **Unfreeze**. After the button: U7: code + PIN or password. | Unfreeze | `cardLast4` (from `ui.prefill`) | App calls `PATCH card/v1/cards/{id}/unfreeze`; shows a local done/failed tile |
| 3.3 | Raise dispute | Gather → inline box | Same as 2.2 | Submit dispute | Same as 2.2 | Same as 2.2 |
| 3.4 | List disputes | Answered in chat | **U2 disputes** — Same as 2.3. | None | None | — |
| 3.5 | Submit complaint | Executed in chat | U1 asks what the complaint is → **U6** (complaint type and text) → done notice that it appears under My Tickets. Show a complaint text box when `payload.pending.service == "submit_complaint"` (§11) | Yes / No (Send on the complaint box) | None | The bot makes the call after Yes |
| 3.6 | My complaints | Answered in chat | **U2 tickets** — Complaint / ticket rows: reference, status, date. | None | None | — |

<!-- UI-TO-BUILD:END -->

## Frontend integration (Dart)

```dart
void renderCardIssue(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'my_tickets':
      final items = (p['complaints'] as List);
      if (items.isNotEmpty) showTicketList(items.cast<Map<String, dynamic>>());
    case 'disputes':
      final items = (p['disputes'] as List);
      if (items.isNotEmpty) showDisputeList(items.cast<Map<String, dynamic>>());
    case 'raise_dispute':
      showDisputeBox(prefill: p);   // U8, as in ATM_SUPPORT.md
    case 'submit_complaint' when p['executed'] == true:
      showSuccessBanner('Complaint submitted');
  }
}
// CONFIRMATION_REQUIRED (complaint) and APP_ACTION (PIN reset, unfreeze) use the
// shared cases in COMMON.md §10.
```

Rendering: tickets and disputes as status rows (reference, date, status chip);
a new complaint is written in the chat: the bot asks what it is about, then shows the yes/no card (U6).
When `CLARIFICATION_REQUIRED` has `payload.pending.service == "submit_complaint"`, show the complaint text box (`COMMON.md` §11).

## Live-verified (2026-10-03, `taslim_islamic`)

- "show my complaints", "any update on my tickets?" → `my_tickets`, "no complaints".
- "my card isnt working" → clarifying question, no service called.
- 2026-10-06 live run: "can u pls reset my card pin?" → `APP_ACTION` `card_pin_reset`; "Can you please unfreeze my card as it has been blocked since last night?" → `APP_ACTION` `card_unfreeze`.

## Known gaps

1. Non-empty complaint/dispute entries not seen live — confirm fields before finalising rows.
2. The wording of the "card isn't working" question varies run to run (LLM-worded); occasionally it adds advice that isn't in the facts.
