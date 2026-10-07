# CARD_REPLACEMENT — Integration Handoff

Status of the customer's card replacement requests. Read `COMMON.md` first.

## Services

| Ask | `category` / `service` | Bank endpoint | Status |
|---|---|---|---|
| Replacement requests (5.1) | `card_info` / `replacement_requests` | `GET card/v1/cards/replacement-requests` | ✅ Live |
| Cancel a request (5.2) | `app_actions` / `replacement_cancel` | — | ✅ App action (`APP_ACTION`, no bank call) |
| Reveal replacement card (5.3) | `app_actions` / `card_details_reveal` | — | ✅ App action, information only (full card numbers are never shown in chat) |

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 5.1 | List replacement requests | Handled in chat: `card_info` / `replacement_requests` |
| 5.2 | Cancel replacement request | App action `replacement_cancel` → `CardReplacementScreen`, `/request_card_replacement` (Info only: the screen needs a `CardReplacementArgs` object, see `COMMON.md` §8) |
| 5.3 | Reveal replacement card details | App action `card_details_reveal` (kind `info`; `CardDetailScreen`, `/card_detail`, Info only) |

Requesting a new replacement for a lost/stolen card is `LOST_OR_STOLEN_CARD.md` (12.1).

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 5.1 | List replacement requests | Answered in chat | **U2 requests** — Replacement requests with status. | None | None | — |
| 5.2 | Cancel replacement request | App action → inline box | **U8** box: The customer's pending replacement requests, each row with a button. After the button: None. | Cancel request (ask to confirm) | None (from `ui.prefill`) | App calls `DELETE card/v1/cards/replacement-requests/{requestId}`; shows a local done/failed tile |

<!-- UI-TO-BUILD:END -->

## How to trigger

Live-tested: "replacement card status", "replacemnt req", "status of my card replacement".
Direct route: `{"message": "show", "category": "card_info", "service": "replacement_requests"}`.
No payload.

## Response — `result.payload` (live)

```json
{"data": {"requests": [], "pagination": {"totalCount": 0, "currentPage": 0,
  "currentPageTotalCount": 0, "hasNext": false}}, "status": "success"}
```
An empty list is the normal "no requests" answer; the bubble says so and never
invents a request.

## Frontend integration (Dart)

```dart
void renderReplacement(ChatTurnResult turn) {
  final reqs = (((turn.payload?['data'] as Map?)?['requests']) as List?) ?? const [];
  if (reqs.isEmpty) return; // bubble already says there are none
  showRequestStatusList(reqs.cast<Map<String, dynamic>>());
}
```

Rendering: status rows (requested date, card ending, status chip). Cancel asks come back as `APP_ACTION` (`replacement_cancel`): show the cancel box from the table above;
reveal asks are information only (U9). Requesting a replacement for a lost card is `LOST_OR_STOLEN_CARD.md`.

## Live-verified (2026-10-03, `taslim_islamic`)

- "replacement card status", "replacemnt req" → `replacement_requests`, "There are currently no replacement requests."

## Known gaps

1. Non-empty request entries not seen live — confirm row fields before finalising.
