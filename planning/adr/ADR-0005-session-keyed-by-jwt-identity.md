# ADR-0005: Session keyed by JWT customer identity, not a caller-supplied session_id

## Status
Accepted

## Context
FR-IDENT-05 requires tying multiple chat turns into one session so follow-ups ("what about
yesterday") resolve correctly. Two approaches: key sessions by the existing (currently unused)
`session_id` request field, letting one customer run multiple independent conversations; or key
sessions solely by the verified JWT subject claim, giving one customer exactly one active
conversation system-wide.

## Decision
Session key = the verified JWT subject claim. Decided directly with the project owner during the
SRS drafting session (2026-08-31). The existing `session_id` field remains in the request schema,
accepted but ignored (see ADR-0007 / SRS §3.5 field-handling decisions).

## Consequences
Simpler implementation — no need to validate or reconcile a caller-supplied identifier against
the authenticated customer. Tradeoff accepted explicitly: a customer active in two places at once
(e.g. two browser tabs, or web + mobile simultaneously) shares one session context rather than
having independent ones — acceptable for this phase per the project owner's choice.

## Alternatives considered
**Caller-supplied `session_id`** — would allow independent concurrent conversations per customer,
at the cost of needing to validate that a `session_id` is only ever used by the customer identity
that created it (to prevent cross-customer session_id collisions/spoofing). Rejected in favor of
the simpler, identity-only approach for this phase.

## Related
FR-IDENT-05..07, F-04
