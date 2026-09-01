# ADR-0011: Fetch the banking taxonomy live from the platform's own catalog endpoints

## Status
Accepted

## Context
ADR-0009 assumed the "official taxonomy" (BRD Open Item 2) would arrive as a document to
transcribe into a static `banking_services.yaml`. On 2026-09-01, the main application's
frontend/backend team provided `user-app-api-map.md`, showing this catalog already exists as a
live API the mobile app itself calls: `GET support/v1/services` (services grid) and
`GET support/v1/pay-transfer` (pay & transfer grid, including nested `subServices`) — each item
carrying a stable `id`, visibility/active flags, and (for pay-transfer) navigation `action` data.

## Decision
Fetch and merge these two endpoints into Polygon Bot's internal taxonomy at startup, refresh
periodically (SRS FR-CATALOG-03/06), and cache the last successful fetch so a refresh failure
doesn't take classification down (NFR-REL-02). Retain the platform's own `id` values as this
system's category/service/subservice identifiers — never re-slugged — so they can be handed
straight back as routing information (ADR-0013).

## Consequences
The taxonomy can never drift from what the mobile app can actually navigate to — there is no
second copy to keep in sync. Introduces two new outbound dependencies (these endpoints must be
reachable, and their auth requirements for a non-mobile-app caller need confirming — SRS Appendix
B item 6, open). Adapter mapping (which subservice uses which integration) still needs to live in
Polygon Bot itself, since the real catalog doesn't carry that information — this is a smaller,
Polygon-Bot-specific config, not the full taxonomy.

## Alternatives considered
**Static YAML (ADR-0009)** — simpler, no runtime dependency on the platform being reachable, but
requires someone to notice and manually transcribe every taxonomy change on the main platform;
rejected now that a live, authoritative source is confirmed to exist.

## Related
FR-CATALOG-01, FR-CATALOG-03, FR-CATALOG-05, FR-CATALOG-06, FR-CATALOG-07, NFR-MAINT-01, NFR-REL-02, F-02
