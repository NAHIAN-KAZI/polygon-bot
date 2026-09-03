# Postman Testing Guide — Polygon Bot API

Manual and scheduled API testing using Postman. Pairs with `HANDOFF.md` (integration
summary) and `INTEGRATION.md` (full contract) — this file is about *how to exercise*
the API, not the contract itself.

Two separate collections — they test different things and hit different servers:

- **Polygon Bot** (`postman/Polygon-Bot.postman_collection.json` +
  `Polygon-Bot.postman_environment.json`) — tests *this chatbot's* `/chat`,
  `/documents`, `/health`. Its banking-route requests include real, live
  category/service ids pulled from the bank platform on 2026-09-01
  (`polygon_services/transaction_history`, `utility/electricity_bill`,
  `payments/card_payment/polygon_bank_card`) alongside the synthetic
  `account_info/balance` entry and a deliberately-invalid one for the
  `UNKNOWN_SERVICE` negative test.
- **Polygon Bank Platform API** (`postman/Polygon-Bank-Platform-API.postman_collection.json`
  + `Polygon-Bank-Platform-API.postman_environment.json`) — tests the bank's own
  dev platform directly (`internet-banking.dev-polygontech.xyz`), bypassing the
  chatbot entirely. The 7 endpoints from `user-app-api-map.md`. Use this to confirm
  what the bank platform itself returns, independent of anything this repo built —
  useful when debugging whether a problem is in the chatbot's adapters or upstream.

## 1. Import

1. Open Postman → **Import** → select all 4 files in `postman/` (both collections,
   both environments).
2. Top-right environment dropdown → select **Polygon Bot - Local/Dev** (switch to
   **Polygon Bank Platform - Dev** when running the other collection).
3. Click the environment's edit (pencil) icon and check:
   - `base_url` — defaults to `http://192.168.12.41:8000`. Change if testing from
     a different network segment (alt IP: `10.10.10.22:8000`). Never `localhost`.
   - `api_key` — defaults to the placeholder `devtestkey123`. Update once the real
     key is issued (see `HANDOFF.md` — it will rotate before go-live).
   - `jwt` — leave blank for now, or fill in a real token from the **Polygon Bank
     Platform API** collection's Login request (see §2a below). Note: banking-service
     requests will return `AUTH_REQUIRED` even with a real, valid token right now —
     the bank hasn't provided the actual JWT signing secret yet, so verification is
     implemented but still fail-closed (expected, not a bug — see `HANDOFF.md`'s
     Known Gaps section).

## 2a. Getting a real test JWT (Polygon Bank Platform API collection)

The **Polygon Bank Platform API** environment needs `test_username`/`test_password`
filled in with real dev-account credentials (get these from the bank's team —
never commit them; the environment file ships with both blank).

1. Select the **Polygon Bank Platform - Dev** environment, fill in `test_username`/
   `test_password`.
2. Run **0. Login (get test JWT)** — on success it saves `jwt`/`refresh_token` into
   that same environment automatically.
3. Copy the `jwt` value from there into the **Polygon Bot** environment's `jwt`
   field to test banking-service routes through the chatbot (Postman doesn't share
   variables across environments automatically — this copy step is manual).
4. The access token is short-lived (~15 minutes) — re-run Login when it expires.

## 2. Run requests

Requests are in the collection in a sensible order:

| Request | What it checks |
|---|---|
| Health Check | `/health` returns `ok`/`degraded` + ollama/qdrant booleans |
| Upload Document | Upload a test file, get back `doc_id` (auto-saved to a collection variable) |
| List Documents | Uploaded doc appears |
| Delete Document | Cleanup, uses the captured `doc_id` |
| Chat - KB Question | Plain question → `token`...`done`, no `result` event |
| Chat - Banking Direct Route | `category`+`service` set → skips classification, returns a `result` event |
| Chat - Ambiguous Request | Vague message → `CLARIFICATION_REQUIRED` |
| Chat - Unknown Service | Bogus category/service → `UNKNOWN_SERVICE`, never `AUTH_REQUIRED`/`BANKING_SERVICE` |

For **Upload Document**: open the request, Body tab, click the `file` field, select
a real `.pdf`/`.docx`/`.txt`/`.md` before sending — Postman can't prefill a file path
from the collection JSON.

Click **Send**, then check the **Test Results** tab (next to the response) — each
request has assertions built in (status code, response shape, expected event/type).
Green = pass.

## 3. Reading the `/chat` SSE stream in Postman

`/chat` responses are `text/event-stream`, not plain JSON. What you see depends on
your Postman version:

- **Postman v10+**: the response panel shows a live "Streaming" view — events appear
  as they arrive, same as a browser would render them.
- **Older Postman**: the full stream only appears once the connection closes, as one
  raw text blob in the response body (this is what the built-in test scripts parse
  with `pm.response.text()` — they don't need the live view to work).

Either way, the raw body looks like:
```
event: token
data: {"token": "The"}

event: token
data: {"token": " refund"}

event: done
data: {}
```
For a banking-service outcome, there's also one `event: result` block before `done` —
see `INTEGRATION.md` for the exact field rules per `result.type`.

## 4. Scheduled / automated checks (not just manual clicking)

Manual Postman runs don't give you ongoing visibility — for that, run this same
collection headlessly on a schedule. Two options:

**Option A — Postman Monitor (hosted, easiest)**
1. Collection menu (`...`) → **Monitor collection**.
2. Set frequency (e.g. every 5 minutes) and add an email/Slack alert on failure.
3. Caveat: this sends `api_key` (and `jwt`, if set) from Postman's cloud to `base_url`.
   Only use this if `base_url` is reachable from the internet and you're comfortable
   with the key transiting Postman's infrastructure — for an internal-only banking
   backend, prefer Option B.

**Option B — Newman (self-hosted CLI runner, recommended for this project)**
Runs the exact same collection/environment files from a cron job on the host itself —
nothing leaves your network.
```bash
npm install -g newman
newman run postman/Polygon-Bot.postman_collection.json \
  -e postman/Polygon-Bot.postman_environment.json \
  --reporters cli,junit --reporter-junit-export newman-report.xml
```
Wire the exit code into your existing alerting (non-zero exit = a request failed its
assertions) via cron + a Slack/email webhook, same pattern as any other health-check
script.

## 5. Security notes

- Don't commit a real `api_key` or `jwt` into `postman/Polygon-Bot.postman_environment.json`
  — it's checked into this repo with only the placeholder values. Keep real secrets in
  a personal, un-committed Postman environment override, or Postman's vault.
- Same for `postman/Polygon-Bank-Platform-API.postman_environment.json`'s `test_username`/
  `test_password`/`jwt`/`refresh_token` — all ship blank. Test-account credentials are
  real, live dev-environment access; treat them like any other secret.
- The `Delete Document` request is destructive — confirm `doc_id` before running it
  against anything other than a test upload.
