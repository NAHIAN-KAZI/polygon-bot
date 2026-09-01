# ADR-0014: Forward the customer's JWT as-is to downstream banking services

## Status
Accepted

## Context
ADR-0012's real adapters need to call the main platform's own banking microservices
(`transfer/`, `polygon-bank/`, `auth/`) on the authenticated customer's behalf. ADR-0008
established that Polygon Bot verifies the JWT it receives, but didn't specify what happens to
that token afterward for an outbound call.

## Decision
Forward the customer's `Authorization: Bearer <JWT>` unmodified to the five real downstream
endpoints (ADR-0012) — no re-minting, no separate service-to-service token. This assumes the
JWT accepted by Polygon Bot is the same token these downstream services already accept via Kong
(the same gateway the mobile app itself goes through) — not yet confirmed with the platform's
auth team (carries forward BRD Open Item 1).

## Consequences
Simplest possible integration — Polygon Bot doesn't need its own service credential or a
token-exchange step for these calls. Entirely dependent on the pass-through assumption holding;
if it doesn't (e.g. these services expect a different audience claim, or reject tokens not
issued through a specific flow), every real adapter call fails and needs rework — this is the
single highest-risk assumption in the real-adapter feature (Features F-05 risk note). A
downstream 401/403 is treated as `AUTH_REQUIRED` rather than `SERVICE_UNAVAILABLE` (ADR-0012),
so a wrong assumption here surfaces as an auth error to the customer, not a silent "unavailable."

## Alternatives considered
**Polygon Bot mints its own service-to-service token per call** — would decouple Polygon Bot
from the customer's exact JWT shape, but requires a token-exchange mechanism that doesn't exist
anywhere in the platform today and wasn't asked for; rejected as unnecessary complexity until the
pass-through assumption is actually shown to fail.

## Related
FR-IDENT-01, FR-INTEG-05, FR-INTEG-06, F-03, F-05
