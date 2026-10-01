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
     they already have an SSE client package in use.
   - Any action buttons/next-screen navigation this intent implies, or an
     explicit note that none apply.
5. **Live-verified** — exact messages tested, dated, with real results.
6. **Known gaps** — anything not confirmed, not covered, or deliberately
   deferred.

## Index

- [FEES.md](FEES.md) — transaction fee/charge quote.
- [ACCOUNT_INFO.md](ACCOUNT_INFO.md) — balance, accounts, device/login
  history, cards, loans, FD/DPS profit history.
- [ATM_SUPPORT.md](ATM_SUPPORT.md) — list disputes (read-only part only;
  cash-by-code/raise-dispute remain blocked/gather-only, not covered here).
