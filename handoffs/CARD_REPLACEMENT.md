# CARD_REPLACEMENT — Integration Handoff

Status of the customer's card replacement requests. Read `COMMON.md` first.

## Services

| Ask | `category` / `service` | Bank endpoint | Status |
|---|---|---|---|
| Replacement requests (5.1) | `card_info` / `replacement_requests` | `GET card/v1/cards/replacement-requests` | ✅ Live |
| Cancel a request (5.2) | — | — | ⛔ Blocked (bot: "only in the app") |
| Reveal replacement card (5.3) | — | — | ❌ Not built on purpose (returns the full card number) |

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
  showRequestStatusList(reqs.cast<Map<String, dynamic>>(),
      onOpen: () => openAppScreen('card_replacement'));
}
```

Rendering: status rows (requested date, card ending, status chip). "Request a
replacement" opens the app's own screen.

## Live-verified (2026-10-03, `taslim_islamic`)

- "replacement card status", "replacemnt req" → `replacement_requests`, "There are currently no replacement requests."

## Known gaps

1. Non-empty request entries not seen live — confirm row fields before finalising.
