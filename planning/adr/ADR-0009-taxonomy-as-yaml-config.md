# ADR-0009: Banking service taxonomy as a YAML config file

## Status
Accepted

## Context
FR-CATALOG-01/03 and NFR-MAINT-01 require the category/service/subservice taxonomy to be
centralized and editable without touching routing/classification code, since the placeholder
taxonomy will be wholesale-replaced by the bank's official one later (BRD Open Item 2).

## Decision
The taxonomy lives in one file, `banking_services.yaml`, loaded and validated at startup
(FR-CATALOG-05); each subservice entry declares its adapter mapping and identity requirement
(FR-CATALOG-04).

## Consequences
Editing the taxonomy is a file edit plus a restart — no database migration, no code change. Fits
the existing deployment (single process, no database beyond Qdrant for vectors) with zero new
infrastructure. Tradeoff: changing the taxonomy requires a redeploy/restart, not a live runtime
update — acceptable, since the taxonomy is expected to change rarely (once, when the official
tree arrives, then infrequently after).

## Alternatives considered
**Database-backed catalog** — would allow live runtime updates without a restart, but adds a new
datastore/schema for a structure that changes rarely, and doesn't fit the current
no-relational-database deployment; rejected as unnecessary complexity for this phase.
**Hardcoded Python structure** — rejected outright; directly violates FR-CATALOG-03's
add/remove/rename-without-code-change requirement.

## Related
FR-CATALOG-01..05, NFR-MAINT-01, F-02
