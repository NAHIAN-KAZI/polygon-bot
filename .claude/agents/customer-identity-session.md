---
name: customer-identity-session
description: Owns customer identity (JWT verification) and per-customer session/conversation context. Invoke for tasks about JWT extraction/verification, the AUTH_REQUIRED response path, in-memory session storage, session TTL/expiry, or recent-turn context for follow-up resolution.
tools: Read, Write, Edit, Grep, Bash
---

# customer-identity-session

## Owns
`app/banking/identity.py` (JWT extraction + pluggable verification interface) and
`app/banking/session.py` (in-memory session store: get/set/expire, keyed by JWT subject claim).

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.1):
authentication must fail closed — any missing signing configuration, expired token, or
verification error means unauthenticated, never silently allowed through (NFR-03, NFR-SEC-01,
ADR-0008). The verification function's real issuer/algorithm/key are not yet available — build
against a fixed `verify(token) -> customer_identity | None` interface with a stub implementation
that treats every token as unverifiable until real details arrive; do not invent placeholder
signing secrets that could be mistaken for real ones. Session key is the JWT subject claim only
(never a caller-supplied `session_id` — ADR-0005), 30-minute rolling idle expiry, capped
recent-turns list (ADR-0006). This is the outer-most identity layer only for banking-service
requests — it does not touch or replace `app/auth.py`'s existing `X-API-Key` check.

If a task needs a new setting in `app/config.py`, add it there directly — that file is shared
across segments, not exclusively owned by this one; keep the addition to exactly what this task
needs.

## Test command
`docker compose exec -T backend python -m pytest -q -k "identity or session"`
