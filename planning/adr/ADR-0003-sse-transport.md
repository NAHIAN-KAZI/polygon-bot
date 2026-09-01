# ADR-0003: SSE as the /chat streaming transport

## Status
Accepted (retroactive)

## Context
Reverse-engineered from `app/routes/chat.py` (`StreamingResponse` with `media_type:
"text/event-stream"`, named events `token`/`done`/`error`) and `INTEGRATION.md`. This extension
adds a new named event (`result`, ADR-0007) to this existing transport rather than introducing a
new one.

## Decision
`/chat` remains a `text/event-stream` response for every request type — KB answers, and now
banking-service/clarification/auth-required/error outcomes alike.

## Consequences
One transport for the whole endpoint keeps the client contract simple (one parser, multiple
named events). Extending it (ADR-0007) is backward compatible by construction — an unrecognized
event name is simply ignored by an existing client.

## Alternatives considered
None at the time this was built — documented here since ADR-0007 depends on this decision
already being in place.

## Related
FR-CONTRACT-01..06, F-06
