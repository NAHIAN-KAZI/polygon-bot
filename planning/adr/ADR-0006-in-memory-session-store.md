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

**Confirmed 2026-09-06 (T-24):** live-reproduced a contamination bug — a single customer's
session (30-min TTL, up to 10 turns) accumulated many unrelated turns across an extended
testing session, and every one of them was being fed into `classify()` as raw prior
messages on every subsequent classification call, regardless of relevance. Symptom:
3 completely different questions ("what is my balance", "how many bank accounts do i
have", "what devices are logged into my account") all returned the *identical* answer to
the first question. Root cause: the recent-turns interface's actual intended purpose
(FR-IDENT-05, "resolve natural follow-ups") is narrow — connecting an earlier clarifying
question to the customer's answer to it — but the call site fed history into every
classification regardless of whether one was actually pending. Fix: a new
`get_classification_context(customer_id)` function (still behind the same get/set
interface this ADR establishes) returns the session's turns only when the most recent
one is itself an unresolved `CLARIFICATION_REQUIRED`/`ACCOUNT_SELECTION_REQUIRED`
outcome — `[]` otherwise. Live re-verified on the exact same, previously-contaminated
session: the same 3 questions now return 3 correct, distinct answers. Does not change
this ADR's core decision (in-memory, keyed by customer_id, swappable interface) — only
scopes *when* history is used.
