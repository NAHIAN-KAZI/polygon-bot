# ADR-0006: In-memory session store behind a swappable interface

## Status
Accepted

## Context
FR-IDENT-05/06 require session context for follow-ups, but the deployment is currently a single
FastAPI/uvicorn process (ADR-0001) with no shared datastore for this purpose. The project owner's
explicit answer during BRD drafting: "for demo do in memory but for future we have to manage."

## Decision
Session context lives only in the running process's memory (a dict keyed by JWT subject claim,
30-minute rolling idle expiry, capped recent-turns list per FR-IDENT-07), behind a small
get/set/expire interface (FR-IDENT-06) so a real backing store can be substituted later without
touching any calling code.

## Consequences
No new infrastructure needed for this phase. Session context is lost on every restart/redeploy,
and does not work across multiple server instances if the deployment ever scales horizontally —
both explicitly accepted tradeoffs for now (BRD Open Item 4), not oversights.

## Alternatives considered
**A shared store now (e.g. Redis)** — would survive restarts and support horizontal scaling
immediately, but is unnecessary infrastructure for a single-process deployment with no current
scaling requirement; rejected for this phase, revisit when/if multi-instance deployment is
actually needed.

## Related
FR-IDENT-05..07, F-04
