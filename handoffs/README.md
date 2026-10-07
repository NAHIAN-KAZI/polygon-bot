# Per-Intent Handoffs

One file per newly-implemented intent (starting with the 14 the API team
supplied), each written the moment that intent's implementation is
live-verified and merged. Not a replacement for the main `HANDOFF.md`/
`INTEGRATION.md` (connection details, auth, SSE mechanics, general rendering
conventions) — these are narrow, intent-specific supplements.

## Required sections, every time

1. **How to trigger it** — natural-language examples + the direct-route
   payload (`category`/`service`/`payload`).
2. **Request payload** — field table (name, type, required, notes).
3. **Response — `result` event** — full example JSON, with notes on any
   unit conversions (poisha vs taka), field meanings, or gaps in what the
   payload contains.
4. **Frontend integration** — how the bank's chatbot frontend should
   actually handle this result in their UI, not just the wire format:
   - Which `result.type`/`service` values to check for in their SSE handler.
   - What to render for a successful result (card, table, plain text —
     recommend the shape that fits the data, and say why).
   - What to render for `CLARIFICATION_REQUIRED`/`SERVICE_UNAVAILABLE` for
     this intent specifically, if it differs from the generic case.
   - A short code snippet showing the parse-and-render logic for this
     specific payload shape — **in Dart**, since the bank's app (and its
     screens referenced in `API_SCREEN_MAP.md`) is Flutter/Dart, not a JS
     web frontend. Use the `http` package's streamed `Request`/`StreamedResponse`
     and manual SSE line parsing (`event:`/`data:`) unless the team confirms
     they already have an SSE client package in use. The shared client is in `COMMON.md`.
   - Any action buttons/next-screen navigation this intent implies, or an
     explicit note that none apply.
5. **Live-verified** — exact messages tested, dated, with real results.
6. **Known gaps** — anything not confirmed, not covered, or deliberately
   deferred.

## Index

Start with **[COMMON.md](COMMON.md)** — request/response contract, every
`result.type`, account/card selection, the secure OTP form, money units, and
the shared Dart client used by every snippet below.

| Intent | Handoff | What's in it |
|---|---|---|
| ACCOUNT_INFO | [ACCOUNT_INFO.md](ACCOUNT_INFO.md) | Accounts, cards, devices, login history, loans, FD/DPS profit |
| ATM_SUPPORT | [ATM_SUPPORT.md](ATM_SUPPORT.md) | Dispute list, raise dispute (gather + redirect), cash-by-code (app only) |
| CARD_ISSUE | [CARD_ISSUE.md](CARD_ISSUE.md) | My tickets/complaints, disputes, vague card problems, blocked fixes |
| CARD_MANAGEMENT | [CARD_MANAGEMENT.md](CARD_MANAGEMENT.md) | Cards, card catalog, limit/virtual card request status, freeze |
| CARD_REPLACEMENT | [CARD_REPLACEMENT.md](CARD_REPLACEMENT.md) | Replacement request status |
| CHECK_BALANCE | [CHECK_BALANCE.md](CHECK_BALANCE.md) | Balance, credit card summary |
| EDIT_PERSONAL_DETAILS | [EDIT_PERSONAL_DETAILS.md](EDIT_PERSONAL_DETAILS.md) | Profile, address/KYC, contacts, change-request status (changes: app only) |
| FAILED_TRANSFER | [FAILED_TRANSFER.md](FAILED_TRANSFER.md) | Raise dispute flow in detail, disputes, tickets |
| FALLBACK | [FALLBACK.md](FALLBACK.md) | Knowledge-base answers, off-topic/abuse handling |
| FEES | [FEES.md](FEES.md) | Transaction fee quote |
| GREETING | [GREETING.md](GREETING.md) | Hello/thanks, quick-reply chips |
| LOST_OR_STOLEN_CARD | [LOST_OR_STOLEN_CARD.md](LOST_OR_STOLEN_CARD.md) | Card freeze with OTP + PIN/password, step by step |
| MINI_STATEMENT | [MINI_STATEMENT.md](MINI_STATEMENT.md) | Transactions, credit card statement |
| TRANSFER | [TRANSFER.md](TRANSFER.md) | Transfers (gather + redirect), beneficiaries, limits, gifts, email/QR history |

Every handoff was checked against live `result` events captured on
2026-10-03 (dev user `taslim_islamic`, `experiments/capture_payloads.py`).

## UI to build

`COMMON.md` §11 defines the UI building blocks (U1–U11) and lists what the backend does not provide yet. Every intent file has a table **"UI to build, use case by use case"**: for each use case, what the customer sees, the buttons, and what is prefilled into which screen. Build from those tables; drive every block from `result.type`, `category`, `service`, `routing` and `payload`, never from the bubble text.
