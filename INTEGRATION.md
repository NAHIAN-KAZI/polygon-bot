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

Request body: `message` (required, 1-4000 chars), `top_k` (optional, 1-20, default 5).

Response: `text/event-stream`, in order:
```
event: sources
data: {"sources": [{"filename": "handbook.pdf", "page": 3, "score": 0.81}, ...]}

event: token
data: {"token": "The"}

event: token
data: {"token": " refund"}

...

event: done
data: {}
```

- `sources` fires once, first — can be `[]` if nothing relevant was found. This is the only place
  citations appear — the answer text itself is plain prose and never contains `[filename]`-style
  citations, so don't parse/strip citations out of the concatenated `token` text.
- `token` repeats — concatenate `.token` in order to build the reply.
- Stream ends with either `event: done` or `event: error` (`{"detail": "..."}`) — always handle
  `error`, don't assume every stream reaches `done`.

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
    // handle event === "sources" | "token" | "done" | "error"
  }
}
```

## Notes

- CORS is open — safe to call directly from a browser on another origin.
- `GET /health` needs no key, returns `{"status": "ok"|"degraded", "ollama": bool, "qdrant": bool}`.
- First request after a server restart can take ~50s (model cold-load) — not an error, just slow once.
