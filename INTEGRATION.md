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

Response: `text/event-stream`. For a plain knowledge-base question, unchanged from before:
```
event: token
data: {"token": "The"}

event: token
data: {"token": " refund"}

...

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
  wants to deep-link instead of just showing the reply text.
- `CLARIFICATION_REQUIRED` — the message was too vague to route; the preceding `token` event is
  the full clarifying question (not a live token stream, just one event). `category`/`service`/
  `subservice`/`payload`/`routing` are all `null`.
- `AUTH_REQUIRED` — the message maps to a real banking service but no valid customer identity was
  presented (missing/invalid `Authorization`, or the downstream service rejected it).
  `category`/`service`/`subservice` are populated, `payload`/`routing` are `null`.
- `UNKNOWN_SERVICE` — the message named a category/service/subservice that isn't a valid path in
  the current taxonomy. `category`/`service`/`subservice` are populated, `payload`/`routing` are
  `null`.
- `SERVICE_UNAVAILABLE` — the request was routed and authorized, but the downstream banking
  service call itself failed. `category`/`service`/`subservice` are populated, `payload`/`routing`
  are `null`.

`result` is never sent for a pure knowledge-base answer — its absence is how a client tells the
two response shapes apart.

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
