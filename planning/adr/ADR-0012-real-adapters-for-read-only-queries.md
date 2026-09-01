# ADR-0012: Real adapters for the 5 subservices with a known live endpoint

## Status
Accepted

## Context
ADR-0010 established a common adapter interface with mock implementations for every subservice,
since no real banking APIs were available at planning time. `user-app-api-map.md` (2026-09-01)
shows five read-only queries already have live, documented endpoints the mobile app itself
calls: balance (`POST transfer/v1/accounting/balance`), transaction history
(`GET transfer/v1/accounting/transaction-list`), account list/detail
(`GET polygon-bank/v1/accounts{/id}`), device history (`GET auth/v1/devices`), and login history
(`GET auth/v1/devices/{id}/login-history`).

## Decision
Implement real adapters for exactly these five subservices, forwarding the customer's verified
JWT as the request's bearer token to the named endpoint and returning the actual response data.
Every other subservice (money transfer, bill payment, card actions, everything without a
documented endpoint) keeps using a mock adapter per ADR-0010 — this doesn't change ADR-0010's
decision, it's the first real implementations behind the same interface it defined.

## Consequences
"What's my balance" and similar read queries now get answered with real data today, not mock
data — a genuine capability upgrade within the existing architecture, with zero change to
classification or the chat contract mechanism (both already treat adapter identity as an
implementation detail). A real adapter's failure is distinguishable from "no real adapter
exists yet": a downstream 401/403 becomes `AUTH_REQUIRED` (the customer's JWT was rejected, not
that the feature isn't built — ADR-0014), while any other failure is `SERVICE_UNAVAILABLE`.
Introduces this system's first outbound calls to the main banking platform (beyond the taxonomy
endpoints) — depends entirely on the JWT-forwarding assumption in ADR-0014.

## Alternatives considered
**Keep mocking these 5 too, for consistency with the rest of the taxonomy** — simpler (one
implementation pattern everywhere), but throws away real, already-available functionality for no
reason; rejected — the project owner explicitly chose to use real data wherever a real endpoint
exists.

## Related
FR-INTEG-01, FR-INTEG-02, FR-INTEG-05, FR-INTEG-06, FR-CONTRACT-08, NFR-REL-01, F-05
