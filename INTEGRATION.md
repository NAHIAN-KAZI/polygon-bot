# Chatbot API — Integration Guide

Base URL: `http://192.168.12.41:8000` (alt IP on same host: `10.10.10.22:8000` if the first isn't
reachable from your network). Do **not** use `localhost` — that only resolves on the server itself.
Auth: every endpoint below requires header `X-API-Key: devtestkey123`.
(placeholder test key — will be rotated to a real secret before go-live, update here when it changes)
No WebSocket — chat is a plain HTTP POST that streams back via SSE.

## Upload a document

```bash
curl -X POST http://192.168.12.41:8000/documents \
  -H "X-API-Key: devtestkey123" \
  -F "file=@handbook.pdf"
```

Accepts `.pdf`, `.docx`, `.txt`, `.md`. Max 25MB.

Response `200`:
```json
{"doc_id": "e8c3...", "filename": "handbook.pdf", "chunk_count": 42}
```

Errors: `400` bad/empty/unparseable file or embedding model rejected a chunk (rare, auto-retried
internally first), `413` too large, `502` backend model/DB actually unreachable, `401` bad key.

Other document endpoints: `GET /documents` (list), `DELETE /documents/{doc_id}` (remove).

## Chat

```bash
curl -N -X POST http://192.168.12.41:8000/chat \
  -H "X-API-Key: devtestkey123" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the refund policy?", "top_k": 5}'
```

Request body: `message` (required, 1-4000 chars), `top_k` (optional, 1-20, default 5),
`session_id` (optional, accepted but currently ignored — session identity comes from the
`Authorization` header instead), `category`/`service`/`subservice` (optional strings — pass all
of `category`+`service` together to skip classification and route directly, per the live banking
service catalog's exact `id` values), `payload` (optional object — extra data for a banking
service call, e.g. `{"amount": 42.5}`).

Optional header: `Authorization: Bearer <jwt>`. Without it (or with a token that doesn't verify),
any banking-service request comes back as `AUTH_REQUIRED` instead of being fulfilled — a plain
knowledge-base question still works with no `Authorization` header at all.

Response: `text/event-stream`. For a plain knowledge-base question, one or more `token`
events, then a single `result` event (`type: "KB_ANSWER"`), then `done`:
```
event: token
data: {"token": "The"}

event: token
data: {"token": " refund"}

...

event: result
data: {"type": "KB_ANSWER", "category": null, "service": null, "subservice": null,
       "payload": {"grounded": true, "hitCount": 5, "sources": ["handbook.pdf"]},
       "routing": null, "version": "1.0"}

event: done
data: {}
```

For anything classified as a banking-service outcome (or a `category`+`service` pair passed
directly in the request), one or more `token` events carrying a short human-readable reply, then
a single `result` event, then `done`:
```
event: token
data: {"token": "Your available balance is 1234.56."}

event: result
data: {"type": "BANKING_SERVICE", "category": "account_info", "service": "balance",
       "subservice": null, "payload": {"balance": 1234.56, ...}, "routing":
       {"category": "account_info", "service": "balance", "subservice": null,
       "action": "redirect"}, "version": "1.0"}

event: done
data: {}
```

`result.type` is one of:
- `BANKING_SERVICE` — the request was fulfilled; `payload` carries the raw fulfillment data,
  `routing` echoes back category/service/subservice plus `action: "redirect"` for a client that
  wants to deep-link instead of just showing the reply text. For a real (non-mock) adapter result,
  `payload` also carries additive display fields alongside the raw ones — never a replacement for
  them: `balance` gains `balanceFormatted` (BDT, e.g. `"৳1,235.50"`). Raw bank money fields
  are **poisha** (1 taka = 100 poisha, except QR payment history, which is taka); every
  `*Formatted` field is already converted to taka (fixed 2026-10-03 — earlier builds showed
  them 100× too high). Each entry under
  `data.accounts` gains `accountNumberMasked`, and each entry under `data.ledgerAccounts` gains
  `identifierMasked` and `balanceFormatted`; each entry under `transactions` gains
  `accountNumberMasked` and `amountFormatted`. Masked fields use `•` for all but the last 4
  characters. The accompanying spoken `token` reply never states a full account/card number —
  only these masked forms, if it needs to reference one. This is enforced at the source: the raw
  fetched data is redacted (`accountNumber`/`identifier` replaced with their masked form,
  `cifNumber`/`nid` stripped, and any 6+ digit run in free-text fields like `description` masked)
  before it is ever shown to the LLM that synthesizes the spoken reply, so the model has no way to
  see — and therefore no way to repeat — a full number. `payload` itself is unaffected by this;
  it still carries the raw + masked fields exactly as described above. Other subservices
  (`device_history`, `login_history`) and mock results (`payload.mock === true`) are unaffected.
  **`category="transfer"`/`service="bank_transfer"` or `"wallet_transfer"` is a special case:
  there is no real adapter for either — a transfer is never executed by this API (ADR-0008's
  standing GET-only policy) — so once the payload is complete (see the `CLARIFICATION_REQUIRED`
  entry below) this result is built directly, with no downstream call at all.** `payload` is the
  full collected payload (`accountNumber`/`amount` for `bank_transfer`, `walletNumber`/`amount`
  for `wallet_transfer`) plus `formattedAmount` (BDT) and `executed: false` — `executed` is
  always `false` here and exists specifically so a client can never mistake this for a completed
  transfer. The `token` reply is a deterministic (not LLM-generated) summary stating the
  collected details and explicitly saying the transfer is not yet done, e.g. *"Here's your
  transfer summary: ৳5,000 to account 1234567890 via Other Bank Transfer. I can't complete this
  for you here — please confirm and finish it in the app."* `routing.action` is
  `f"{subservice}_transfer"` (e.g. `"other_bank_transfer"`, `"own_account_transfer"`,
  `"city_account_transfer"`, `"bkash_transfer"`, `"nagad_transfer"`, `"rocket_transfer"`,
  `"upay_transfer"`) — a specific, frontend-resolvable navigation hint (same pattern as
  `BENEFICIARY_MATCH`'s `routing.action`) for the client to deep-link into the real app screen
  that actually completes the transfer.
  **`category="service_requests"`/`service="raise_dispute"` is the same kind of special case:**
  there is no real submission either — this request is never POSTed to
  `service-request/v1/disputes` (the real endpoint behind ATM_SUPPORT 2.2, CARD_ISSUE 3.3, and
  FAILED_TRANSFER 8.2 — one shared contract, one implementation) — so once the payload is
  complete this result is built directly, with no downstream call at all. `payload` is the full
  collected payload (`accountNumber`, `transactionReferenceNo`, `remarks`) plus `executed: false`.
  The `token` reply is a deterministic (not LLM-generated) summary stating the collected details
  and explicitly saying the dispute hasn't been filed, e.g. *"Here's your dispute summary:
  transaction TXN-998877 on account 1234567890, reason: ATM debited my account but no cash was
  dispensed. I can't submit this for you here — please confirm and complete it in the app."*
  `routing.action` is `"raise_dispute"` and `routing.subservice` is always `null` (this service
  has no subservices). Note: `category="service_requests"`/`service="raise_dispute"` is not yet a
  valid taxonomy path as of this writing — a direct-route request naming it explicitly currently
  comes back `UNKNOWN_SERVICE` until `banking-service-catalog` adds the taxonomy entry; this
  branch is otherwise fully implemented and will activate as soon as that entry exists (the
  existing, unrelated `category="service_requests"`/`service="disputes"` read-only list path is
  unaffected and already live).
- `CLARIFICATION_REQUIRED` — the message was too vague to route; the preceding `token` event is
  the full clarifying question (not a live token stream, just one event). `category`/`service`/
  `subservice`/`payload`/`routing` are all `null`. This also covers a routed-but-incomplete
  banking-service request: `category="fees"`/`service="fee_quote"` requires
  `payload.transactionType` and `payload.amount`; `category="transfer"`/`service="bank_transfer"`
  requires `payload.accountNumber` and `payload.amount`; `category="transfer"`/
  `service="wallet_transfer"` requires `payload.walletNumber` and `payload.amount`;
  `category="service_requests"`/`service="raise_dispute"` requires `payload.accountNumber`,
  `payload.transactionReferenceNo`, and `payload.remarks` (the reason for the dispute). If any
  required field is missing (whether the message was routed here directly or via classification)
  the response is a `CLARIFICATION_REQUIRED` asking specifically for whichever piece is missing,
  rather than a `SERVICE_UNAVAILABLE`/silently-incomplete `BANKING_SERVICE` — this is checked
  deterministically before any downstream call is ever attempted. *Which* fields are missing is
  always decided deterministically; only the *wording* of the question is generated by the
  language model (so it reads naturally and varies, e.g. *"How much would you like to send via
  bKash?"*), naming back already-known details (account/wallet numbers only ever as "ending
  1234") and asking only for what's missing. It never asks for a PIN, password, or OTP. If
  generation fails or produces anything unsafe, a fixed template question is sent instead —
  either way, never rely on the exact wording of this `token`. The
  customer's very next message is then also resolved deterministically (no LLM re-classification)
  whenever it's a bare numeric reply to this specific kind of clarification (e.g. "2000", "2000
  taka", "5,000 tk") — the still-missing `amount` is parsed straight out of that reply and merged
  into the payload the guard already knew, rather than re-deriving category/service from scratch.
  If the reply instead has zero or 2+ numbers in it, or answers a *different* still-missing field
  (only `amount` has an extractor today), this deterministic step is skipped and the message is
  classified normally, exactly as before. This only ever applies to a reply following *this*
  guard's own `CLARIFICATION_REQUIRED` — a genuinely ambiguous `CLARIFICATION_REQUIRED` (freeform
  `ask_clarification`, wire-identical: `category`/`service`/`subservice`/`payload`/`routing` all
  `null`) is unaffected and always goes through the normal classification path for the next
  message too.
- `AUTH_REQUIRED` — the message maps to a real banking service but no valid customer identity was
  presented (missing/invalid `Authorization`, or the downstream service rejected it).
  `category`/`service`/`subservice` are populated, `payload`/`routing` are `null`.
- `UNKNOWN_SERVICE` — the message named a category/service/subservice that isn't a valid path in
  the current taxonomy. `category`/`service`/`subservice` are populated, `payload`/`routing` are
  `null`.
- `SERVICE_UNAVAILABLE` — the request was routed and authorized, but the downstream banking
  service call itself failed. `category`/`service`/`subservice` are populated, `payload`/`routing`
  are `null`.
- `ACCOUNT_SELECTION_REQUIRED` — the request needed an account/ledger-account identifier the
  customer didn't supply (e.g. `balance`, `transaction_history`, `fd_profit_history`,
  `dps_profit_history`), and the customer has more than one matching account (if they have
  exactly one, this is skipped automatically and the request just succeeds). `category`/
  `service`/`subservice` are populated, `routing` is `null`. `payload` is one of two shapes
  depending on which kind of account the service needed, passed through verbatim:
  - Regular bank accounts (`balance`, `transaction_history`, ...): `{"accounts":
    [{"accountNumber", "accountName", "accountType", "balance"}, ...]}` — full account numbers
    are included here for the client's resubmit, even though the accompanying `token` text only
    shows a masked last-4 form.
  - Ledger accounts (`fd_profit_history`, `dps_profit_history`): `{"accounts":
    [{"identifier", "chartOfAccountName"}, ...]}` — the accompanying `token` text shows
    `chartOfAccountName` plus a masked last-6-characters form of `identifier`.

  To resolve either shape: have the customer pick one entry from `payload.accounts` and resubmit
  using the same direct-route mechanism described above — `category`+`service` (+`subservice` if
  present) exactly as returned, with `payload.accountNumber` (regular accounts) or
  `payload.identifier` (ledger accounts) set to the chosen entry's full value. No new request
  field or endpoint. Free-text follow-ups like "the savings one" are not resolved automatically in
  this version — only a structured resubmit with an explicit `accountNumber`/`identifier` is
  supported.
- `CONFIRMATION_REQUIRED` — a deliberate explicit yes/no gate in front of beneficiary add
  (`category="polygon_services"`/`service="beneficiary_add"`), one of this chatbot's two
  mutating banking actions (the other, card freeze, uses the OTP step-up described under
  `OTP_REQUIRED` below instead of a yes/no) — every other banking service this API fulfills is
  read-only or (for `transfer`) gather-only-never-executes; these two are the sole,
  explicitly user-approved exceptions. The preceding `token` event states exactly what
  will happen in plain language (naming back a masked account number) and ends
  with "Shall I proceed? (yes/no)". `category`/`service`/`subservice` are populated,
  `payload` carries the collected, not-yet-submitted details (`{"nickname",
  "accountNumber", "serviceType", "identifierType"}`), `routing` is `null`. The customer's very next plain-text message is resolved
  deterministically (never by LLM judgment) against two small, literal phrase sets —
  affirmative (`"yes"`, `"confirm"`, `"confirmed"`, `"do it"`, `"go ahead"`,
  `"yes please"`) or negative (`"no"`, `"cancel"`, `"nevermind"`, `"never mind"`,
  `"stop"`), case/trailing-punctuation-insensitive. Anything else is "unclear" and
  re-asks the same question (still `CONFIRMATION_REQUIRED`, same `payload`) rather than
  ever guessing. An explicit `category`+`service` resubmit is always treated as a fresh
  request, never as answering a pending confirmation. Only an unambiguous "yes" actually
  calls the real adapter:
  - Affirmative + the call succeeds: `result.type` is `BANKING_SERVICE`, `payload` is
    the adapter's response data plus `executed: true`, `routing.action` is `"redirect"`.
  - Affirmative + the call fails: surfaces as `AUTH_REQUIRED` or `SERVICE_UNAVAILABLE`
    exactly like any other adapter failure elsewhere in this doc — never a false
    success.
  - Negative: `result.type` is `BANKING_SERVICE`, `payload` is `{"executed": false,
    "cancelled": true}` — the real adapter is never called.

  Beneficiary add's gather step is the existing `CLARIFICATION_REQUIRED` mechanism:
  `payload.nickname` and `payload.accountNumber` are both required before confirmation;
  `serviceType`/`identifierType` are filled in automatically (`"OTHER_BANK"`/
  `"ACCOUNT_NUMBER"`) — this conversational flow currently only supports adding an
  other-bank beneficiary by account number, not an MFS wallet or other beneficiary type.
- `OTP_REQUIRED` — card freeze (`category="card_services"`/`service="frezz_unfrezz"`) is
  waiting for the bank's OTP + PIN/password step-up. This replaces a yes/no for freeze: the
  submitted OTP + PIN/password *is* the confirmation.

  **Gather step:** if the request doesn't already carry `payload.cardId`, the customer's
  cards are listed first (0 cards → a clean `BANKING_SERVICE` reply, nothing to freeze; 1
  card → auto-selected; 2+ → `ACCOUNT_SELECTION_REQUIRED`, same mechanism/shape as the
  `account_info` section above, described as e.g. "Debit card ending 0251"). Once a specific
  card is known, a missing `payload.reason` triggers an ordinary `CLARIFICATION_REQUIRED`
  (free-text, no fixed enum).

  **OTP sent:** once card + reason are known, the API sends a one-time code by SMS to the
  phone number of the logged-in customer. That number always comes from the customer's own
  verified `Authorization` token; any phone number in the request is ignored. The `token`
  event (fixed text) asks for the code plus either the card PIN or the login password.
  `result`:
  ```
  {"type": "OTP_REQUIRED", "category": "card_services", "service": "frezz_unfrezz",
   "subservice": null, "routing": null, "version": "1.0",
   "payload": {"cardId": "41", "cardLast4": "0251", "reason": "lost",
               "otpRequired": true, "credentialOptions": ["pin", "password"],
               "verificationStatus": "OTP_SENT"}}
  ```
  Show a secure form: an OTP field (when `otpRequired` is `true`) plus **one** of PIN or
  password.

  **Submitting the OTP + PIN/password (frontend request shape):**
  ```bash
  curl -N -X POST http://192.168.12.41:8000/chat \
    -H "X-API-Key: devtestkey123" -H "Authorization: Bearer <jwt>" \
    -H "Content-Type: application/json" \
    -d '{"message": "Submit verification", "payload": {"otp": "123456", "pin": "1234"}}'
  ```
  - Use the same `Authorization` token as the rest of the conversation (the pending step is
    tied to the customer's session). `message` is required by the schema but is never read
    for credentials, so send any fixed text such as `"Submit verification"`.
  - `payload.otp`: the SMS code. `payload.pin` **or** `payload.password`: exactly one, never
    both. These are accepted **only** as structured `payload` fields. A code or PIN typed
    into `message` is never parsed, never passed to the language model, and never logged.
  - Sending `category`/`service` is optional. If you send them, they must be
    `card_services`/`frezz_unfrezz` and the payload must contain the credentials, or the
    request is treated as a new request.
  - `"cancel"` (or any negative phrase from the `CONFIRMATION_REQUIRED` list) with no
    credentials cancels: `BANKING_SERVICE`, `payload: {"executed": false, "cancelled": true}`.
  - pin/password/otp are never logged, never stored in session state, and never echoed back
    in any `result`.

  **Outcomes of a submission** (`payload.verificationStatus` tells the form what to do):
  | Situation | `result.type` | `verificationStatus` | What to show |
  |---|---|---|---|
  | Success | `BANKING_SERVICE` | — | token *"Done — your card ending 0251 has been frozen."*; `payload` = bank response + `executed: true`; `routing.action: "redirect"` |
  | Missing OTP or PIN/password | `OTP_REQUIRED` | `CREDENTIALS_MISSING` | re-show form |
  | Both PIN and password sent | `OTP_REQUIRED` | `CREDENTIALS_INVALID_COMBINATION` | re-show form, one credential only |
  | Wrong OTP | `OTP_REQUIRED` | `OTP_INCORRECT` (+ `attemptsRemaining` when known) | re-enter the **same** code; no new code is sent |
  | OTP expired / not on record | `OTP_REQUIRED` | `OTP_RESENT` | a new code was sent automatically; clear the OTP field |
  | Too many wrong OTPs (blocked ~5 min) | `BANKING_SERVICE` | `OTP_BLOCKED` (`executed: false`) | flow ended; ask the customer to wait, then start again |
  | Too many OTP sends requested | `BANKING_SERVICE` | `SEND_THROTTLED` (`executed: false`) | flow ended; wait a few minutes |
  | Wrong PIN/password | `OTP_REQUIRED` | `INVALID_CREDENTIALS`, `otpRequired: false` | ask **only** for PIN or password again; the verified code is still valid (kept server-side), so no new code |
  | Verification expired/used | `OTP_REQUIRED` | `OTP_RESENT` | a new code was sent automatically |
  | Bank/SMS service down | `SERVICE_UNAVAILABLE` | — | — |
  | Bank rejected the session | `AUTH_REQUIRED` | — | — |
- `KB_ANSWER` — a plain knowledge-base question (including an off-topic/vulgar message that gets a
  banking-only decline instead of a real answer — both are this same type, distinguished only by
  `payload.grounded`). `category`/`service`/`subservice`/`routing` are all `null`. `payload` is
  `{"grounded": bool, "hitCount": int, "sources": [<filenames>] | null}` — `grounded` is true iff
  at least one knowledge-base chunk was retrieved for the question; `hitCount` is how many;
  `sources` is a deduplicated, order-preserving list of the source document filenames those chunks
  came from when `grounded` is true, or `null` (never `[]`) when it's false.

`result` is sent exactly once for every outcome above, including `KB_ANSWER` — a client no longer
needs to infer the response shape from whether a `result` event showed up; every stream that
reaches `done` carries exactly one `result` event first.

- `token` repeats — concatenate `.token` in order to build the reply. Answer text is plain prose,
  no markdown, no `[filename]`-style citations or page numbers — there is no separate sources/
  citations event either.
- Stream ends with either `event: done` or `event: error` (`{"detail": "..."}`) — always handle
  `error`, don't assume every stream reaches `done`. `error` is currently only emitted on the
  knowledge-base path (embedding/vector-store/generation failures); banking-service failures
  surface as a `result` event (`SERVICE_UNAVAILABLE`/`AUTH_REQUIRED`), not `error`.

Minimal JS client:
```js
const res = await fetch("http://192.168.12.41:8000/chat", {
  method: "POST",
  headers: { "X-API-Key": "devtestkey123", "Content-Type": "application/json" },
  body: JSON.stringify({ message: "What is the refund policy?" }),
});
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buf = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  let i;
  while ((i = buf.indexOf("\n\n")) !== -1) {
    const chunk = buf.slice(0, i);
    buf = buf.slice(i + 2);
    const event = chunk.match(/^event: (.+)$/m)?.[1];
    const data = JSON.parse(chunk.match(/^data: (.+)$/m)?.[1] ?? "{}");
    // handle event === "token" | "done" | "error"
  }
}
```

## Notes

- CORS is open — safe to call directly from a browser on another origin.
- `GET /health` needs no key, returns `{"status": "ok"|"degraded", "ollama": bool, "qdrant": bool}`.
- First request after a server restart can take ~50s (model cold-load) — not an error, just slow once.
