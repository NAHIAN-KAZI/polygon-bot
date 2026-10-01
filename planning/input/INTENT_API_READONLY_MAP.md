# Intent → API Map (read-only vs mutating)

Consolidated from `planning/input/Internet Banking API cURL Reference.md` (the
bank API team's 14-intent cURL reference, 46 endpoints total). Standing
policy this session: **GET-only** — no mutating (POST/PUT/PATCH/DELETE) call
has ever been executed against the real platform; that was an explicit
user decision (see TASKS.md, "GET-only for now").

One exception worth knowing: **CHECK_BALANCE's balance lookup is a `POST`**
even though it's a pure read — the account number goes in the JSON body,
not a query param. It's read-only in effect, just not read-only by HTTP
verb. Flagged inline below.

Legend: ✅ = read-only (GET), ⛔ = mutating (POST/PUT/PATCH/DELETE — never
called), ⚠️ = read-effect-but-POST (the one exception), 🚫 = no backend
exists (per the doc, dead end regardless of verb).

## 1. ACCOUNT_INFO — *implemented (as `account_info` real intent)*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 1.1 | `polygon-bank/v1/accounts` | GET | ✅ |
| 1.2 | `polygon-bank/v1/accounts/{id}` | GET | ✅ |
| 1.3 | `polygon-bank/v1/accounts/by-number/{number}` | GET | ✅ |
| 1.4 | `polygon-bank/v1/accounts/by-username/{username}` | GET | ✅ |
| 1.5 | `polygon-bank/v1/accounts/{id}/quick-view` (star) | PUT | ⛔ |
| 1.6 | `loan/v1/loans` | GET | ✅ |
| 1.7 | `product/v1/fixed-deposit/{id}/profit-history` | GET | ✅ |
| 1.8 | `product/v1/dps/{id}/profit-history` | GET | ✅ |

## 2. ATM_SUPPORT — *not implemented*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 2.1 | `transfer/v1/cash-by-code` | POST | ⛔ |
| 2.2 | `service-request/v1/disputes` (raise) | POST | ⛔ |
| 2.3 | `service-request/v1/disputes` (list) | GET | ✅ |

## 3. CARD_ISSUE — *not implemented*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 3.1 | `card/v1/cards/{id}/reset-pin` | PATCH | ⛔ |
| 3.2 | `card/v1/cards/{id}/unfreeze` | PATCH | ⛔ |
| 3.3 | `service-request/v1/disputes` (raise) | POST | ⛔ |
| 3.4 | `service-request/v1/disputes` (list) | GET | ✅ |
| 3.5 | `support/v1/complaints` (submit) | POST | ⛔ |
| 3.6 | `support/v1/complaints` (list, "my complaints") | GET | ✅ |

## 4. CARD_MANAGEMENT — *partially implemented (mock-only: `card_services`)*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 4.1 | `card/v1/cards/{id}/freeze` | PATCH | ⛔ |
| 4.2 | `card/v1/cards/{id}/unfreeze` | PATCH | ⛔ |
| 4.3 | `card/v1/cards/{id}/close` | PATCH | ⛔ |
| 4.4 | `card/v1/cards/{id}/contactless` | PATCH | ⛔ |
| 4.5 | `card/v1/cards/{id}/international-transaction` | PATCH | ⛔ |
| 4.6 | `card/v1/cards/{id}/reset-pin` | PATCH | ⛔ |
| 4.7 | `card/v1/cards/{id}/limit-change-requests` (submit) | POST | ⛔ |
| 4.8 | `card/v1/cards/limit-change-requests` (list) | GET | ✅ |
| 4.9 | `card/v1/cards/limit-change-requests/{id}` (cancel) | DELETE | ⛔ |
| 4.10 | `card/v1/card-products` | GET | ✅ |
| 4.11 | `card/v1/cards/debit` (apply) | POST | ⛔ |
| 4.12 | `card/v1/cards/debit/{id}/reveal` | GET | ✅ (sensitive — reveals card details) |
| 4.13 | `card/v1/cards/prepaid` (apply) | POST | ⛔ |
| 4.14 | `card/v1/cards/prepaid/{id}/reveal` | GET | ✅ (sensitive) |
| 4.15 | `card/v1/cards/virtual/requests` (submit) | POST | ⛔ |
| 4.16 | `card/v1/cards/virtual/requests` (list) | GET | ✅ |
| 4.17 | `card/v1/cards/virtual/requests/{id}` (cancel) | DELETE | ⛔ |
| 4.18 | `card/v1/cards/virtual/requests/{id}/reveal` | GET | ✅ (sensitive) |
| 4.19 | `card/v1/cards/{id}/quick-view` (star) | PUT | ⛔ |
| 4.20 | `card/v1/cards/{id}/credit-card/payment` | POST | ⛔ |
| 4.21 | `bill/v1/payment/card_payment` | POST | ⛔ |
| 4.22 | `auth/v1/user/qr-settings/cards` (list) | GET | 🚫 no backend |
| 4.23 | `auth/v1/user/qr-settings/cards/{id}` (enable/disable) | PUT | 🚫 no backend |

## 5. CARD_REPLACEMENT — *not implemented*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 5.1 | `card/v1/cards/replacement-requests` (list) | GET | ✅ |
| 5.2 | `card/v1/cards/replacement-requests/{id}` (cancel) | DELETE | ⛔ |
| 5.3 | `card/v1/cards/replacement-requests/{id}/reveal` | GET | ✅ (sensitive) |

## 6. CHECK_BALANCE — *implemented (overlaps `account_info`/`balance`)*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 6.1 | `transfer/v1/accounting/balance` | **POST** | ⚠️ read-effect, body-based lookup |
| 6.2 | `card/v1/cards/{id}/credit-summary` | GET | ✅ |

## 7. EDIT_PERSONAL_DETAILS — *not implemented*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 7.1 | `auth/v1/user` (get profile) | GET | ✅ |
| 7.2 | `auth/v1/user/profile/nickname` | PATCH | ⛔ |
| 7.3 | `auth/v1/user/profile/image` (PATCH variant) | PATCH | ⛔ |
| 7.4 | `auth/v1/user/profile/image` (POST variant) | POST | ⛔ |
| 7.5 | `auth/v1/auth/mobile/update` | POST | ⛔ |
| 7.6 | `auth/v1/auth/email/update` | POST | ⛔ |
| 7.7 | `customer/v1/me/demographic` (get address) | GET | ✅ |
| 7.8 | `customer/v1/me/demographic` (update address) | PATCH | ⛔ |
| 7.9 | `customer/v1/me/kyc` (submit) | POST | ⛔ |
| 7.10 | `customer/v1/me/contacts` | GET | ✅ |
| 7.11 | `service-request/v1/profile-changes` (submit) | POST | ⛔ |
| 7.12 | `service-request/v1/profile-changes` (list) | GET | ✅ |
| 7.13 | `service-request/v1/contact-priority` (submit) | POST | ⛔ |
| 7.14 | `service-request/v1/contact-priority` (list) | GET | ✅ |

## 8. FAILED_TRANSFER — *not implemented*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 8.1 | `transfer/v1/accounting/transaction-list` | GET | ✅ |
| 8.2 | `service-request/v1/disputes` (raise) | POST | ⛔ |
| 8.3 | `service-request/v1/disputes` (list) | GET | ✅ |
| 8.4 | `support/v1/complaints` (submit) | POST | ⛔ |
| 8.5 | `support/v1/complaints` (list) | GET | ✅ |

## 9. FALLBACK — *implemented (KB/decline path, no bank API)*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 9.1 | `support/v1/ai/chat` (logged in) | POST | ⛔ (not used — we have our own RAG) |
| 9.2 | `support/v1/ai/public/chat` | POST | ⛔ (not used) |
| 9.3 | `support/v1/ai/status` (logged in) | GET | ✅ (not used) |
| 9.4 | `support/v1/ai/public/status` | GET | ✅ (not used) |
| 9.5 | `support/v1/faq-categories` | GET | ✅ (not used) |
| 9.6 | `support/v1/faqs` | GET | ✅ (not used) |
| 9.7 | `support/v1/complaints` (submit) | POST | ⛔ |

## 10. FEES — *implemented (real intent, `fees`/`fee_quote`)*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 10.1 | `transfer/v1/transaction-type/charge-with-amount` | GET | ✅ |

## 11. GREETING — *implemented (no API, chatbot-handled directly)*
No endpoints.

## 12. LOST_OR_STOLEN_CARD — *not implemented*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 12.1 | `card/v1/cards/{id}/replacement-requests` (report) | POST | ⛔ |
| 12.2 | `card/v1/cards/{id}/freeze` (immediate) | PATCH | ⛔ |

## 13. MINI_STATEMENT — *implemented (overlaps `polygon_services`/`transaction_history`)*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 13.1 | `transfer/v1/accounting/transaction-list` | GET | ✅ |
| 13.2 | `polygon-bank/v1/accounts/{id}/transactions` | GET | ✅ |
| 13.3 | `card/v1/cards/{id}/statements` | GET | ✅ |
| 13.4 | `report/v1/expense-tracker/categories/{ref}/transactions` | GET | ✅ |

## 14. TRANSFER — *not implemented (mock-only: `transfer`/`bank_transfer`, `wallet_transfer`, `polygon_services`/`beneficiary` is real though)*
| # | Endpoint | Verb | R/W |
|---|---|---|---|
| 14.1 | `transfer/v1/bank-transfer/own-account` | POST | ⛔ |
| 14.2 | `transfer/v1/bank-transfer/city-bank` | POST | ⛔ |
| 14.3 | `transfer/v1/bank-transfer/other-bank` | POST | ⛔ |
| 14.4 | `transfer/v1/other-banks` (list) | GET | 🚫 no backend |
| 14.5 | `transfer/v1/bank-transfer/gift` | POST | ⛔ |
| 14.6 | `transfer/v1/bank-transfer/gift/received` | GET | ✅ |
| 14.7 | `transfer/v1/transactions/do-transaction` | POST | ⛔ |
| 14.8 | `transfer/v1/accounting/linked-account` | POST | ⛔ |
| 14.9 | `transfer/v1/email-transfer` (create) | POST | ⛔ |
| 14.10 | `transfer/v1/email-transfer` (list) | GET | ✅ |
| 14.11 | `transfer/v1/email-transfer/{id}` (details) | GET | ✅ |
| 14.12 | `transfer/v1/email-transfer/{id}/cancel` | POST | ⛔ |
| 14.13 | `transfer/v1/email-transfer/{id}/resend-notification` | POST | ⛔ |
| 14.14 | `transfer/v1/wallet-transfer` | POST | ⛔ |
| 14.15 | `transfer/v1/wallet-transfer/verify` | GET | ✅ |
| 14.16 | `merchant/v1/qr/pay` | POST | ⛔ |
| 14.17 | `merchant/v1/qr/parse` | POST | ⛔ |
| 14.18 | `merchant/v1/qr/history` | GET | ✅ |
| 14.19 | `beneficiary/v1/beneficiaries` (list) | GET | ✅ — **real, implemented** |
| 14.20 | `beneficiary/v1/beneficiaries` (add) | POST | ⛔ |
| 14.21 | `beneficiary/v1/beneficiaries/{id}` (edit) | PATCH | ⛔ |
| 14.22 | `beneficiary/v1/beneficiaries/{id}` (delete, soft) | DELETE | ⛔ |
| 14.23 | `beneficiary/v1/beneficiaries/{id}/photo` (upload) | PATCH | ⛔ |
| 14.24 | `beneficiary/v1/beneficiaries/{id}/photo` (remove) | DELETE | ⛔ |
| 14.25 | `beneficiary/v1/beneficiaries/{id}/pin` | PATCH | ⛔ |
| 14.26 | `polygon-bank/v1/accounts/by-number/{id}` (recipient lookup) | GET | ✅ (same as 1.3) |
| 14.27 | `transfer/v1/my-limit/{account}` (get) | GET | ✅ |
| 14.28 | `transfer/v1/my-limit/{account}` (request change) | PUT | ⛔ |
| 14.29 | `transfer/v1/my-limit/pending/{id}` (cancel) | DELETE | ⛔ |

## Totals
- 46 endpoints across 14 intents (13 with APIs; GREETING has none).
- **GET (read-only): 28** — all available under the current policy.
- **Mutating (POST/PUT/PATCH/DELETE): 17** — none ever called live; blocked by standing policy.
- **1 exception** (CHECK_BALANCE, 6.1): POST verb, but read-only in effect.
- **2 dead ends**: 4.22/4.23 (QR card settings), 14.4 (other-banks list) — ⚠️ NO BACKEND per the bank's own doc, unusable regardless of GET-only policy.

## What's actually real today (as of T-55)
Of the 28 read-only endpoints above, only these are wired to a real adapter
in this codebase right now — everything else in the table is reference
material for future intents, not yet built:
- `account_info`: balance, accounts, device_history, login_history (own
  endpoints, not all from this doc — see `app/banking/adapters/real.py`)
- `polygon_services`: transaction_history, beneficiary (14.19)
- `fees`/`fee_quote` (10.1)
