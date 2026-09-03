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

## Known gaps — read before testing

1. **JWT verification is implemented but not yet active.** Algorithm/claim shape are confirmed (HS256, `sub`=customer phone number, `iss`="internet-banking", no `aud`, ~15-min token lifetime) — but the actual shared HS256 signing secret hasn't been provided by the bank's auth team yet. Until it is, every banking-service request correctly returns `AUTH_REQUIRED`, even with a real, valid, unexpired token — this was live-verified. Plain KB questions work today regardless of this.
2. **`X-API-Key` is a placeholder.** Will rotate before go-live. Do not ship `devtestkey123` in any client.
3. **Base URL is internal-network only.** Confirm it's reachable from wherever your client actually runs.

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
