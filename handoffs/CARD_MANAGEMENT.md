# CARD_MANAGEMENT — Integration Handoff

The customer's cards, the bank's card catalog, card request statuses, and
card freeze. Read `COMMON.md` first. Freeze is detailed in
`LOST_OR_STOLEN_CARD.md` (same flow).

## Services

| Ask | `category` / `service` | Bank endpoint | Status |
|---|---|---|---|
| My cards | `account_info` / `cards` | from `GET polygon-bank/v1/accounts` | ✅ Live |
| Freeze a card (4.1) | `card_services` / `frezz_unfrezz` | `PATCH card/v1/cards/{id}/freeze` | ✅ Live-verified (approved exception) |
| Card catalog (4.10) | `card_info` / `card_products` | `GET card/v1/card-products` | ✅ Live |
| Limit-change requests (4.8) | `card_info` / `card_limit_requests` | `GET card/v1/cards/limit-change-requests` | ✅ Live |
| Virtual card requests (4.16) | `card_info` / `virtual_card_requests` | `GET card/v1/cards/virtual/requests` | ✅ Live |

Blocked — the bot says "this can only be done in the app": unfreeze (4.2),
close card, contactless/international on/off, PIN reset, limit change
submit/cancel, apply for debit/prepaid/virtual cards, star card, credit card
bill payment. Not built on purpose: card-detail "reveal" endpoints (4.12/4.14/4.18
return full card numbers — unsafe in a chat). QR payment cards (4.22/4.23): no backend.

## How to trigger

Live-tested: "cards", "my crads", "which credit cards do you offer",
"virtual card request status", "did my card limit change go through",
"unfreeze my card" (→ app only), "reset my card pin" (→ app only).

Direct route: `{"message": "show", "category": "card_info", "service": "card_products"}`.

## Request payload

| Service | Field | Notes |
|---|---|---|
| `card_products` | `cardCategory`, `scheme`, `domesticNetwork`, `internationalNetwork` | Optional filters |
| others | — | No payload |

## Response — `result.payload` (live, 2026-10-03)

**cards** — see `ACCOUNT_INFO.md` (`{"cards": [{"id", "cardNumber" (masked), "cardType", "status", ...}]}`).

**card_products** (fees in poisha; `null` = no fee):
```json
{"data": [
  {"id": 1, "tierName": "Classic Debit", "cardCategory": "DEBIT", "scheme": "VISA", "bin": "400123",
   "capabilities": ["ATM", "POS"], "domesticNetworks": ["NPSB"], "internationalNetworks": [],
   "physicalEligible": true, "virtualEligible": true, "active": true,
   "issuanceFeePoisha": null, "vatPoisha": null, "totalPoisha": null},
  {"id": 2, "tierName": "GOLD", "cardCategory": "CREDIT", "scheme": "VISA",
   "capabilities": ["ATM", "CONTACTLESS", "ECOMMERCE", "POS"], "...": "..."}]}
```

**card_limit_requests / virtual_card_requests** (empty for the dev user):
```json
{"data": {"requests": [], "pagination": {"totalCount": 0, "currentPage": 0, "hasNext": false}}, "status": "success"}
```

## Frontend integration (Dart)

```dart
void renderCardManagement(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'card_products':
      showProductCarousel([
        for (final c in (p['data'] as List))
          if (c['active'] == true)
            CardProduct(
              name: c['tierName'],
              category: c['cardCategory'],
              scheme: c['scheme'],
              features: (c['capabilities'] as List).cast<String>(),
              fee: c['totalPoisha'] == null ? 'No fee' : Money.fromPoisha(c['totalPoisha']).format(),
            )
      ]);
    case 'card_limit_requests':
    case 'virtual_card_requests':
      final reqs = ((p['data'] as Map)['requests'] as List);
      reqs.isEmpty ? showEmpty('No requests') : showRequestStatusList(reqs);
  }
}
```

Rendering: products as a carousel of cards (name, category, features, fee);
request lists as status rows (date, type, status chip). "Apply"/"Change limit"
buttons, if shown, open the app's own screens — the bot never submits them.

## Live-verified (2026-10-03, `taslim_islamic`)

- "cards", "my crads" → card ending 0293.
- "which credit cards do you offer" → `card_products` (Classic Debit, GOLD credit).
- Request statuses → "there are none".
- "unfreeze my card", "reset my card pin" → "can only be done in the app", no service called.

## Known gaps

1. The catalog reply wording sometimes mixes debit and credit cards ("two credit cards: Classic Debit is not a credit card…") — the data is right; render from `payload`.
2. Non-empty request lists not seen live — confirm row fields before finalising.
