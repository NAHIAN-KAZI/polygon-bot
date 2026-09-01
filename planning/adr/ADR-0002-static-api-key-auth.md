# ADR-0002: Static shared API key as the outer auth gate

## Status
Accepted (retroactive)

## Context
Reverse-engineered from `app/auth.py` (11 lines: compares `X-API-Key` header against one
`settings.API_KEY` env var; no-op if unset) and `INTEGRATION.md` (documents this as the sole auth
mechanism for the current external integration team). This extension adds JWT-based customer
identity (ADR-0008) as a second, independent layer on top of this — it does not replace it.

## Decision
Every `/chat` and `/documents` call continues to require the existing `X-API-Key` header,
unchanged. This is the outer gate proving the caller is a legitimate integration; JWT (ADR-0008)
is an inner layer proving which customer, checked only when a request needs one.

## Consequences
Existing external integration team requires zero change. The two auth layers are independent —
a request can have a valid API key and no/invalid JWT (fine for KB questions, `AUTH_REQUIRED` for
banking-service ones), but never the reverse (no valid API key means the request never reaches
JWT checking at all, unchanged from today).

## Alternatives considered
Replacing the API key with JWT-only auth — rejected: breaks the existing integration team, who
have no JWT and aren't expected to (they're a system integration, not an authenticated customer
session).

## Related
FR-IDENT-01..04, F-03
