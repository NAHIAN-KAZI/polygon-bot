---
name: chat-api-contract
description: Owns the /chat endpoint's request/response contract — ChatRequest schema, the SSE event stream, and the new result event. Invoke for tasks about extending ChatRequest fields, adding/changing SSE events, or wiring classification/identity/adapter output into the /chat response.
tools: Read, Write, Edit, Grep, Bash
---

# chat-api-contract

## Owns
`app/routes/chat.py` — the existing `/chat` endpoint, including the `ChatRequest` model and the
SSE event stream it produces.

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.1,
`planning/SRS.md` §3.5, and ADR-0007): `message` stays the only mandatory field, spelled exactly
as today — no rename to `text`, no dual-accept (confirmed decision). `category`/`service`/
`subservice`/`payload` are new optional fields. `session_id` stays in the schema, accepted but
ignored (session identity now comes from the JWT via `customer-identity-session`, not this
field). A request containing only `message` must behave byte-for-byte identically to today
(FR-CONTRACT-02) — this is the single highest-regression-risk file in the whole project; when in
doubt, re-read `INTEGRATION.md` before changing anything here.

New `result` SSE event: emitted once, after all `token` events and before `done`, for every
non-KB outcome (`BANKING_SERVICE`, `CLARIFICATION_REQUIRED`, `AUTH_REQUIRED`, `UNKNOWN_SERVICE`,
`SERVICE_UNAVAILABLE`) — never for a pure KB answer. Payload: `{type, category, service,
subservice, payload, routing, version}`, `version` starting at `"1.0"` (FR-CONTRACT-04). This
segment orchestrates calls into `conversation-routing`, `customer-identity-session`, and
`banking-service-integration` — it does not reimplement their logic.

After this segment's changes, always update `INTEGRATION.md` to match (it's the contract the
external integration team relies on) and note the update in the PR/task summary.

## Test command
`docker compose exec -T backend python -m pytest -q -k chat`
