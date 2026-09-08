# Polygon Bot — Integration Handoff

Short reference for the frontend/backend team consuming this API. Full contract: `INTEGRATION.md` (this repo root).

## Connection

- Base URL: `http://192.168.12.41:8000` (alt: `10.10.10.22:8000`). Never `localhost`.
- Auth header: `X-API-Key: devtestkey123` (placeholder — rotates before go-live, do not hardcode).
- No WebSocket. `/chat` streams via SSE over plain HTTP POST.
- CORS open. `/health` needs no key.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/documents` | Upload doc. Multipart `file`. pdf/docx/txt/md, max 25MB. |
| GET | `/documents` | List docs. |
| DELETE | `/documents/{doc_id}` | Remove doc. |
| POST | `/chat` | RAG + banking-service chat. Streams SSE. |
| GET | `/health` | No auth. `{status, ollama, qdrant}`. |

## POST /chat — request body

| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | string | yes | 1–4000 chars |
| `top_k` | int | no | 1–20, default 5 |
| `session_id` | string | no | accepted, ignored — identity comes from `Authorization` |
| `category` | string | no | pass with `service` to skip classification, route directly |
| `service` | string | no | see above |
| `subservice` | string | no | optional, used with category+service |
| `payload` | object | no | extra data for a banking-service call, e.g. `{"amount": 42.5}` |

Header `Authorization: Bearer <jwt>` — optional. Required for a banking-service request to actually fulfill; a plain KB question works without it.

## SSE events

| Event | Data | When |
|---|---|---|
| `token` | `{"token": string}` | repeats — concatenate in order for full reply |
| `result` | see below | once, banking-service outcomes only — never for a plain KB answer |
| `done` | `{}` | stream end, success |
| `error` | `{"detail": string}` | stream end, failure — KB path only |

Always handle both `done` and `error` — a stream is not guaranteed to reach `done`.

## result event — fields

`type`, `category`, `service`, `subservice`, `payload`, `routing`, `version`.

## result.type values

| type | category/service/subservice | payload | routing |
|---|---|---|---|
| `BANKING_SERVICE` | set | fulfillment data | `{category, service, subservice, action:"redirect"}` |
| `CLARIFICATION_REQUIRED` | null | null | null — preceding `token` is the full clarifying question |
| `AUTH_REQUIRED` | set | null | null — missing/invalid JWT, or downstream rejected it |
| `UNKNOWN_SERVICE` | set | null | null — not a valid category/service/subservice path |
| `SERVICE_UNAVAILABLE` | set | null | null — routed and authorized, downstream call failed |
| `ACCOUNT_SELECTION_REQUIRED` | set | `{accounts:[...]}` | null — pick one and resubmit via direct route with `payload.accountNumber` |

## Known gaps — read before testing

1. **JWT verification is live.** It verifies real tokens via the bank's own `GET /auth/v1/auth/session` introspection endpoint (not local signature checking — the bank doesn't hand out its signing secret). A real, valid, unexpired bearer token now successfully authenticates — live-verified end to end, including a real `BANKING_SERVICE` response with real account data. An invalid/expired/missing token correctly returns `AUTH_REQUIRED`.
2. **Multi-account resolution is structured-only in v1.** If a customer has 2+ accounts and doesn't specify which for `balance`/`transaction_history`, the response is `ACCOUNT_SELECTION_REQUIRED` with the full list in `payload.accounts`; the client must resubmit with `payload.accountNumber` set. Free-text follow-ups like "the savings one" are not resolved automatically. If the customer has exactly 1 account, this is skipped automatically — no extra step needed.
3. **Classification latency**: a typical natural-language banking request now resolves in ~2-6 seconds end to end (recently switched the classification model for speed and accuracy — was previously 15-50s). Plain KB questions are unaffected by this and stream as before.
4. **`login_history` always requires `payload.deviceId`.** There's no way to fetch it "for the account overall" — the underlying endpoint is scoped per-device. Get a `deviceId` from a prior `device_history` call's `payload.devices[].deviceId`, then pass it explicitly: `payload: {"deviceId": "..."}`. Without it, this always returns `SERVICE_UNAVAILABLE` — not a bug.
5. **`X-API-Key` is a placeholder.** Will rotate before go-live. Do not ship `devtestkey123` in any client.
6. **Base URL is internal-network only.** Confirm it's reachable from wherever your client actually runs.

## Frontend rendering guide (for cards/tables/UI)

This API returns **JSON only, over SSE — never HTML.** Table/card layout,
styling, and rendering are entirely your frontend's job; this API just gives
you the structured data to render.

1. **Masked numbers**: banking-service `payload` fields include additive
   `*Masked` companions next to the raw field (e.g. `accountNumberMasked`
   alongside `accountNumber`, `identifierMasked` alongside `identifier`) —
   `"••••••••0015"` style, last 4 digits visible. **Use the `*Masked` field
   for display; never render the raw number.** The spoken `token` reply also
   never states a full number.
2. **Currency formatting**: `*Formatted` companion fields (e.g.
   `balanceFormatted`, `amountFormatted`) give a ready-to-display BDT string,
   e.g. `"৳100,225,505"`. Raw numeric fields are unchanged alongside them.
3. **Date-range tables** (transaction/login history): pass
   `payload.startDate` and `payload.endDate` (ISO `YYYY-MM-DD`, both
   required together) on the request. The response includes `dateFiltered:
   true` and only in-range records when this worked. Omit both fields for
   the default most-recent-N view (unchanged, existing behavior). There is
   no free-text date parsing — a message like "last 20 days" typed in chat
   does **not** auto-apply a filter; the caller must set the explicit fields
   (e.g. from a date picker).
4. **Action buttons**: no new field needed for this — `result.service` /
   `result.subservice` (already returned on every `BANKING_SERVICE` result)
   is enough to resolve the right action/route through your own app's
   existing local service catalog, the same way the main services grid
   already does.
5. **Beneficiary details**: not yet a real integration — `beneficiary`
   currently returns a generic placeholder (`payload.mock: true`). Blocked
   until you share the real beneficiary-list endpoint/shape; flag it back to
   us once you have it.

## Example — plain KB question

```bash
curl -N -X POST http://192.168.12.41:8000/chat \
  -H "X-API-Key: devtestkey123" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the refund policy?"}'
```

## Example — direct banking-service route

```bash
curl -N -X POST http://192.168.12.41:8000/chat \
  -H "X-API-Key: devtestkey123" \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"category": "account_info", "service": "balance", "payload": {"accountNumber": "123"}}'
```

## Minimal JS client

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
    // handle event === "token" | "result" | "done" | "error"
  }
}
```
