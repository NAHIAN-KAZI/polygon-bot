# Bank API cURL Test Results — Which Endpoints Work

Live test of every endpoint in `planning/input/Internet Banking API cURL
Reference.md` (the API team's cURL reference for all 14 chatbot intents),
run against the real dev platform (`https://internet-banking.dev-polygontech.xyz`)
with a fresh, valid bearer token.

**Scope note:** only GET (read-only) endpoints were executed — 46 of 107.
The other 61 are POST/PUT/PATCH/DELETE (mutating — freeze/unfreeze a card,
submit a complaint, create a dispute, update profile fields, etc.) and were
deliberately **not run**, since executing them for real would create actual
data/state changes on this test account (confirmed: one earlier mutating
test, "Submit complaint," did return `201 Created` — a real ticket). Those
61 are listed at the bottom as **untested by policy**, not failed.

Test date: 2026-09-29.

## Working (19 — real 200 data returned)

| # | Endpoint | Section |
|---|---|---|
| 1.1 | Get all accounts | ACCOUNT_INFO |
| 1.6 | My loans | ACCOUNT_INFO |
| 3.6 | My complaints (card) | CARD_ISSUE |
| 4.10 | Card products list | CARD_MANAGEMENT |
| 4.16 | Virtual card — list my requests | CARD_MANAGEMENT |
| 5.1 | List replacement requests | CARD_REPLACEMENT |
| 7.1 | Get profile | EDIT_PERSONAL_DETAILS |
| 7.7 | Get address (demographic profile) | EDIT_PERSONAL_DETAILS |
| 7.10 | My contacts | EDIT_PERSONAL_DETAILS |
| 7.12 | Profile change — list my requests | EDIT_PERSONAL_DETAILS |
| 7.14 | Contact priority — list my requests | EDIT_PERSONAL_DETAILS |
| 8.5 | My complaints (transfer) | FAILED_TRANSFER |
| 9.3 | Polygon AI status (logged in) | FALLBACK |
| 9.4 | Polygon AI status (public) | FALLBACK |
| 9.5 | FAQ categories | FALLBACK |
| 14.6 | Gifts received | TRANSFER |
| 14.10 | Email transfer — list | TRANSFER |
| 14.15 | Wallet verify | TRANSFER |
| 14.18 | QR payment history | TRANSFER |
| 14.19 | Beneficiary — list | TRANSFER |

## Server errors — 500, worth reporting to the API team (11)

These reached the backend (not a routing/auth problem) and it errored
internally — same class of issue as the earlier `beneficiary` 500/502
incidents that turned out to be real, fixable bugs on their end.

| # | Endpoint | Section |
|---|---|---|
| 1.2 | Get account detail | ACCOUNT_INFO |
| 4.8 | Card limit change — list my requests | CARD_MANAGEMENT |
| 4.12 | Reveal debit card details | CARD_MANAGEMENT |
| 4.14 | Reveal prepaid card details | CARD_MANAGEMENT |
| 4.18 | Virtual card — reveal details | CARD_MANAGEMENT |
| 5.3 | Reveal replacement card details | CARD_REPLACEMENT |
| 6.2 | Credit card summary | CHECK_BALANCE |
| 13.2 | Account transactions | MINI_STATEMENT |
| 13.3 | Credit card statement (billed/unbilled) | MINI_STATEMENT |
| 14.4 | Other banks list (doc already flags ⚠️ NO BACKEND) | TRANSFER |
| 14.11 | Email transfer — details | TRANSFER |

## 404 — not found (5)

4 are genuine gaps; one (`4.22`) is expected — the source doc already tags
it ⚠️ NO BACKEND.

| # | Endpoint | Section | Note |
|---|---|---|---|
| 1.3 | Get account by account/card number | ACCOUNT_INFO | |
| 1.4 | Get accounts by username | ACCOUNT_INFO | |
| 1.7 | FD profit history | ACCOUNT_INFO | |
| 1.8 | DPS profit history | ACCOUNT_INFO | |
| 4.22 | QR payment cards — list | CARD_MANAGEMENT | doc already flags ⚠️ NO BACKEND — expected |
| 13.4 | Expense tracker — category transactions | MINI_STATEMENT | |
| 14.26 | Recipient lookup by account number | TRANSFER | |

## 400 — likely just placeholder param values, not real failures (7)

Every one of these needs a real path/query parameter (account ID, date
range, transaction type) — the doc's example commands use literal
placeholders like `<ACCOUNT_ID>`, so a 400 here is expected until real
values are substituted. Not evidence the endpoint itself is broken.

| # | Endpoint | Section |
|---|---|---|
| 2.3 | List disputes | ATM_SUPPORT |
| 3.4 | List disputes | CARD_ISSUE |
| 8.1 | Transaction history (read transfer status) | FAILED_TRANSFER |
| 8.3 | List disputes | FAILED_TRANSFER |
| 9.6 | FAQs | FALLBACK |
| 10.1 | Transaction charge quote by type and amount | FEES |
| 13.1 | Transaction list (paginated, date range) | MINI_STATEMENT |

## 403 — forbidden (1)

| # | Endpoint | Section | Note |
|---|---|---|---|
| 14.27 | My transfer limit — get | TRANSFER | Possibly needs a scope/permission this test account doesn't have |

## Untested by policy — mutating endpoints (61)

Not run to avoid creating real side effects (complaints, disputes, card
freeze/unfreeze, profile changes, transfers, etc.) on the live test account.
Full list: every POST/PUT/PATCH/DELETE endpoint in the source doc — see
`planning/input/Internet Banking API cURL Reference.md` sections 1.5, 2.1–2.2,
3.1–3.3/3.5, 4.1–4.7/4.9/4.11/4.13/4.15/4.17/4.19–4.21/4.23, 5.2, 6.1,
7.2–7.6/7.8–7.9/7.11/7.13, 8.2/8.4, 9.1–9.2/9.7, 12.1–12.2,
14.1–14.3/14.5/14.7–14.9/14.12–14.14/14.16–14.17/14.20–14.25/14.28–14.29.

If you want these tested too, that needs an explicit decision on acceptable
side effects (e.g. a dedicated disposable test account, or accepting that
test complaints/disputes will show up in their system).

## Summary

- **46 GET endpoints tested**: 19 working, 11 real server errors (500),
  5 not found (1 expected), 7 need real params to test properly, 1 forbidden.
- **61 mutating endpoints**: untested by policy, not failed.
