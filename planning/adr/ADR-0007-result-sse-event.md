# ADR-0007: Extend SSE with a `result` event, not a single JSON response

## Status
Accepted

## Context
Banking-service outcomes (FR-CONTRACT-03) are a structured JSON payload, not a token-by-token
generated answer — raising a real fork on how `/chat` should deliver them: keep every response
type on the existing SSE transport (ADR-0003) by adding a new named event, or switch to a single
synchronous JSON response (no streaming) whenever the outcome isn't a KB answer. The project
owner's explicit direction: keep token streaming as today, and send the structured JSON once the
stream finishes.

## Decision
Add one new SSE event, `event: result`, carrying `{type, category, service, subservice, payload,
routing, version}`. Emitted after all `token` events (if any) and before `done`, for every
non-pure-KB outcome (`BANKING_SERVICE`, `CLARIFICATION_REQUIRED`, `AUTH_REQUIRED`,
`UNKNOWN_SERVICE`, `SERVICE_UNAVAILABLE`). Pure KB answers emit no `result` event at all
(FR-CONTRACT-02).

## Consequences
Fully backward compatible by construction (ADR-0003) — an existing client parsing only
`token`/`done`/`error` is unaffected; it simply never sees `result`. One transport, one client
mental model, for every response type. The `version` field (FR-CONTRACT-04) gives the receiving
team a way to detect future shape changes to this event without breaking silently.

## Alternatives considered
**Single synchronous JSON response for non-KB types** — simpler for a client that doesn't want to
deal with SSE parsing for structured lookups, but splits `/chat`'s response contract into two
shapes depending on outcome type, and was explicitly rejected by the project owner in favor of
keeping one consistent streaming transport.

## Related
FR-CONTRACT-01..06, F-06
