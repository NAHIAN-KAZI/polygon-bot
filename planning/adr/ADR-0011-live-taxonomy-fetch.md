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

## Amendment 2026-09-01 (T-19): a narrow, deliberate exception for non-navigable account features

T-09 found that only `transaction_history` of the 5 planned real-adapter subservices (BRD/SRS
"balance, transaction history, accounts, device history, login history") actually exists in the
live-fetched catalog — the other 4 are direct account features the mobile app calls without ever
navigating through the services/pay-transfer grid, so they will never appear in
`support/v1/services` or `support/v1/pay-transfer` no matter how the platform's catalog evolves.

This ADR's "never invent or hardcode a taxonomy entry" principle is about not second-guessing or
duplicating the platform's own navigable catalog — it was never meant to make these 4 real,
existing, always-available account features permanently unclassifiable just because they aren't
navigation-grid items. Decision: append a small, fixed set of synthetic entries (`account_info`
category: `balance`, `accounts`, `device_history`, `login_history`) to the taxonomy after each
live fetch, alongside — never replacing or shadowing — the fetched data. This is a narrow,
named exception, not a reopening of the static-YAML approach ADR-0009 rejected: the fetched
catalog remains the sole source for every navigable service; only these 4 fixed, non-navigable
account features are ever added synthetically, and they're documented here precisely so this
doesn't grow into an uncontrolled parallel taxonomy later.

## Related
FR-CATALOG-01, FR-CATALOG-03, FR-CATALOG-05, FR-CATALOG-06, FR-CATALOG-07, NFR-MAINT-01, NFR-REL-02, F-02
