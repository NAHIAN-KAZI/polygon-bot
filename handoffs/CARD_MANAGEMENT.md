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

Every other card change (unfreeze, close, contactless/international, PIN reset,
limit change, card applications, star, bill payment) is an `APP_ACTION`: no bank call,
the app gets the screen to open. Card-detail reveals (4.12/4.14/4.18) are information only:
full card numbers are never shown in chat. QR payment cards (4.22/4.23): no backend.

## What the bot does for each request in this intent

"Open" / "Info only" applies the `APP_ACTION` rule in `COMMON.md` §8.

| Row | Request | Outcome |
|---|---|---|
| 4.1 | Freeze card | Executed in chat after yes/no **and** a code: `card_services` / `frezz_unfrezz` (card pick → reason → `CONFIRMATION_REQUIRED` → Yes → `OTP_REQUIRED` → freeze). Details in `LOST_OR_STOLEN_CARD.md` |
| 4.2 | Unfreeze card | App action `card_unfreeze` → `FreezeCardScreen`, `/freeze_card` (Open). Prefill: `cardLast4` |
| 4.3 | Close card | App action `card_close` → `CardReplacementScreen`, `/request_card_replacement` (Info only). Prefill: `cardLast4` |
| 4.4 | Contactless on/off | App action `card_contactless` → `CardDetailScreen`, `/card_detail` (Info only). Prefill: `cardLast4` |
| 4.5 | International use on/off | App action `card_international` → `SelectCardForInternationalScreen`, `/international_transaction/select_card` (Open). Prefill: `cardLast4` |
| 4.6 | Reset card PIN | App action `card_pin_reset` → `SelectCardForPinResetScreen`, `/set_reset_card_pin` (Open). Prefill: `cardLast4` |
| 4.7 | Limit change — submit | App action `card_limit_change` → `CardLimitChangeScreen`, `/card_limit_change_request` (Info only). Prefill: `cardLast4`, `requestedLimit` (taka) |
| 4.8 | Limit change — list | Handled in chat: `card_info` / `card_limit_requests` |
| 4.9 | Limit change — cancel | App action `card_limit_cancel` → `CardLimitChangeScreen`, `/card_limit_change_request` (Info only) |
| 4.10 | Card products | Handled in chat: `card_info` / `card_products` |
| 4.11 | Apply for debit card | App action `card_apply` → `CardProductCatalogScreen`, `/card_product_catalog` (Open). Prefill: `cardType` |
| 4.12 | Reveal debit card details | App action `card_details_reveal` (kind `info`; `CardDetailScreen`, `/card_detail`, Info only). Details never shown in chat |
| 4.13 | Apply for prepaid card | App action `card_apply` (as 4.11) |
| 4.14 | Reveal prepaid card details | App action `card_details_reveal` (as 4.12) |
| 4.15 | Virtual card — submit | App action `card_apply` (as 4.11) |
| 4.16 | Virtual card — list | Handled in chat: `card_info` / `virtual_card_requests` |
| 4.17 | Virtual card — cancel | App action `card_virtual_cancel` (kind `info`, no screen in the app) |
| 4.18 | Virtual card — reveal | App action `card_details_reveal` (as 4.12) |
| 4.19 | Star card | App action `quick_view_star` → `CustomizeQuickViewScreen`, `/customize_quick_view` (Open) |
| 4.20 | Credit card bill payment (own card) | App action `credit_card_pay` → `CardDetailScreen`, `/card_detail` (Info only). Prefill: `paymentType` |
| 4.21 | Credit card bill payment (another bank's card) | App action `other_card_pay` → `CardPaymentDetailsScreen`, `/card_payment/details/:type` (Info only). Prefill: `amount` (taka), `cardNumberLast4` |
| 4.22 | QR payment cards — list | Not available: app action `qr_payment_cards`, kind `unavailable` (no backend) |
| 4.23 | QR payment card — enable/disable | Not available: app action `qr_payment_cards`, kind `unavailable` (no backend) |
| — | My cards | Handled in chat: `account_info` / `cards` |

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 4.1 | Freeze card | Executed in chat | Card picker (U5) if several cards → U1 asks the reason → **U6** (card ending, reason) → **U7** (code + PIN or password) → U1 done notice | Yes / No, Verify / Cancel | None (the bot knows the card) | The bot makes the call after the code |
| 4.2 | Unfreeze card | App action → inline box | **U8** box: Frozen cards (preselected from `cardLast4`) each with **Unfreeze**. After the button: U7: code + PIN or password. | Unfreeze | `cardLast4` (from `ui.prefill`) | App calls `PATCH card/v1/cards/{id}/unfreeze`; shows a local done/failed tile |
| 4.3 | Close card | App action → inline box | **U8** box: Card (preselected) with a warning that closing is permanent. After the button: U7: code + PIN or password. | Close card · Keep | `cardLast4` (from `ui.prefill`) | App calls `PATCH card/v1/cards/{id}/close`; shows a local done/failed tile |
| 4.4 | Contactless on/off | App action → inline box | **U8** box: Card tile with a contactless on/off switch and an optional limit field. After the button: None. | Save | `cardLast4` (from `ui.prefill`) | App calls `PATCH card/v1/cards/{id}/contactless` with `enabled` (and `limitPoisha`); shows a local done/failed tile |
| 4.5 | International transaction on/off | App action → inline box | **U8** box: Card (preselected) with an international-use on/off switch. After the button: U7: code + PIN or password. | Save | `cardLast4` (from `ui.prefill`) | App calls `PATCH card/v1/cards/{id}/international-transaction` with `enabled`; shows a local done/failed tile |
| 4.6 | Reset card PIN | App action → inline box | **U8** box: Card (preselected from `cardLast4`, else the card picker) with a **Reset PIN** button. After the button: U7: code + PIN or password. | Reset PIN | `cardLast4` (from `ui.prefill`) | App calls `PATCH card/v1/cards/{id}/reset-pin`; shows a local done/failed tile |
| 4.7 | Limit change — submit | App action → inline box | **U8** box: Form: credit card (preselected), new limit in taka, optional reason. After the button: None. | Submit request | `cardLast4`, `requestedLimit` (from `ui.prefill`) | App calls `POST card/v1/cards/{id}/limit-change-requests` with `requestedCreditLimitPoisha` (taka × 100); the bank reviews it; shows a local done/failed tile |
| 4.8 | Limit change — list | Answered in chat | **U2 requests** — Limit-change requests with their status. | None | None | — |
| 4.9 | Limit change — cancel | App action → inline box | **U8** box: The customer's pending limit-change requests, each row with a button. After the button: None. | Cancel request (ask to confirm) | None (from `ui.prefill`) | App calls `DELETE card/v1/cards/limit-change-requests/{requestId}`; shows a local done/failed tile |
| 4.10 | Card products list | Answered in chat | **U2 products** — Card products (name, type, scheme). Optional **Apply** button that sends the message `Apply for a card` (opens the apply box). | See text | None | — |
| 4.11 | Apply for debit card | App action → inline box | **U8** box: Form: card type (debit, prepaid or virtual), product picker, account to link, name on the card; prepaid also the load amount. After the button: U7: code + PIN or password for debit and prepaid; none for virtual. | Apply | `cardType` (from `ui.prefill`) | App calls `POST card/v1/cards/debit` · `.../prepaid` · `.../virtual/requests`; shows a local done/failed tile |
| 4.13 | Apply for prepaid card | App action → inline box | **U8** box: Form: card type (debit, prepaid or virtual), product picker, account to link, name on the card; prepaid also the load amount. After the button: U7: code + PIN or password for debit and prepaid; none for virtual. | Apply | `cardType` (from `ui.prefill`) | App calls `POST card/v1/cards/debit` · `.../prepaid` · `.../virtual/requests`; shows a local done/failed tile |
| 4.15 | Virtual card — submit | App action → inline box | **U8** box: Form: card type (debit, prepaid or virtual), product picker, account to link, name on the card; prepaid also the load amount. After the button: U7: code + PIN or password for debit and prepaid; none for virtual. | Apply | `cardType` (from `ui.prefill`) | App calls `POST card/v1/cards/debit` · `.../prepaid` · `.../virtual/requests`; shows a local done/failed tile |
| 4.16 | Virtual card — list | Answered in chat | **U2 requests** — Virtual card requests with status. | None | None | — |
| 4.17 | Virtual card — cancel | App action → info | **U9** info card: "Cancel virtual card". The app has no screen for cancelling a virtual card at the moment. | None | None | No app screen for this |
| 4.19 | Star card | App action → inline box | **U8** box: Accounts and cards, each with a star switch; the one named in the message starts switched on. After the button: None. | Star switch | None (from `ui.prefill`) | App calls `PUT polygon-bank/v1/accounts/{id}/quick-view` · `PUT card/v1/cards/{id}/quick-view?isStarred=`; shows a local done/failed tile |
| 4.20 | Credit card bill payment (card service) | App action → inline box | **U8** box: Credit card (preselected) + what to pay (total outstanding, statement due or minimum due) + account to pay from. After the button: None (the app adds its own idempotency key). | Pay | `cardLast4`, `paymentType` (from `ui.prefill`) | App calls `POST card/v1/cards/{id}/credit-card/payment`; shows a local done/failed tile |
| 4.21 | Credit card bill payment (bill service) | App action → inline box | **U8** box: Form: card number to pay (last digits prefilled), amount, account to pay from, note. After the button: U7: code + transaction PIN. | Pay | `amount`, `cardNumberLast4` (from `ui.prefill`) | App calls `POST bill/v1/payment/card_payment`; shows a local done/failed tile |
| 4.22 | QR payment cards — list | Not available | **U9** info card: QR payment card settings are not available at the moment. | None | None | No backend |
| 4.23 | QR payment card — enable/disable | Not available | **U9** info card: QR payment card settings are not available at the moment. | None | None | No backend |

<!-- UI-TO-BUILD:END -->

## How to trigger

Live-tested: "cards", "my crads", "which credit cards do you offer",
"virtual card request status", "did my card limit change go through".
Change requests ("unfreeze my card", "close my card", "apply for a debit card") return `APP_ACTION`.

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

## Card freeze: yes/no before the code

Freeze (4.1) asks for an explicit yes **before** any verification code is sent:

1. Which card: one card → used automatically; several → `ACCOUNT_SELECTION_REQUIRED`
   (card entries; send `{"cardId": id}`).
2. Why, if the customer didn't say (`CLARIFICATION_REQUIRED`).
3. `CONFIRMATION_REQUIRED`, `payload: {"cardId", "cardLast4", "reason"}`. No code sent yet.
4. Yes (`{"confirm": true}`) → the code is sent → `OTP_REQUIRED` (code + card PIN or
   login password). No → `{"executed": false, "cancelled": true}`, nothing sent.
5. Form submitted → `BANKING_SERVICE` `{"executed": true, "cardId", "cardLast4", "status"}`.

A request to unfreeze is never turned into a freeze: it returns `APP_ACTION` `card_unfreeze`.

## Live-verified (2026-10-03, `taslim_islamic`)

- "cards", "my crads" → card ending 0293.
- "which credit cards do you offer" → `card_products` (Classic Debit, GOLD credit).
- Request statuses → "there are none".
- 2026-10-06 live run: "unfreeze", "Close card", "cncl my card pls" → `APP_ACTION` (`card_unfreeze`, `card_close`); no bank call.

## Known gaps

1. The catalog reply wording sometimes mixes debit and credit cards ("two credit cards: Classic Debit is not a credit card…") — the data is right; render from `payload`.
2. Non-empty request lists not seen live — confirm row fields before finalising.
3. Very short or misspelt asks can be misread. In the 2026-10-06 live run, "free my card" got the
   freeze yes/no instead of `card_unfreeze`. The yes/no step means nothing happens unless the customer says yes.
4. `prefill` is passed to the target screens, but most of them don't read it yet (app side).
