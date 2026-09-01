---
name: banking-service-catalog
description: Owns the banking category/service/subservice taxonomy — its live fetch, cache, and refresh logic. Invoke for tasks about fetching/merging the platform's real service catalog, taxonomy caching/refresh behavior, or mapping a platform service id to its adapter/identity-requirement.
tools: Read, Write, Edit, Grep, Bash
---

# banking-service-catalog

## Owns
`app/banking/taxonomy.py` (fetches and merges `GET support/v1/services` + `GET support/v1/pay-transfer`
into one internal taxonomy, caches it, and periodically refreshes) and `app/banking/adapter_map.py`
(the Polygon-Bot-owned mapping from each platform service `id` to its adapter name and whether it
requires customer identity — the real catalog doesn't carry this, so it's maintained here).

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.2,
`planning/SRS.md` v0.2 §3.2, and ADR-0011 — **superseding ADR-0009's static-YAML approach**):

- Taxonomy is fetched live from the platform's own `support/v1/services` and
  `support/v1/pay-transfer` endpoints — there is no local `banking_services.yaml` to hand-edit.
  Never invent or hardcode a taxonomy entry; if a subservice is missing from the real catalog, it
  doesn't exist for classification purposes.
- Retain the platform's own `id` string for every category/service/subservice exactly as
  returned — never re-slugged or renamed. This is what makes routing responses work without a
  translation layer (ADR-0013) — do not "clean up" or reformat these ids.
- Exclude any entry with `isActive: false` from what's offered to classification (FR-CATALOG-07).
- Refresh periodically (e.g. every 15 minutes); if a refresh fetch fails, keep serving the last
  successfully cached result and log the failure — never let a refresh failure make
  classification unavailable (FR-CATALOG-06, NFR-REL-02). Fail startup loudly only if there is no
  cache yet and the initial fetch fails.
- Taxonomy must remain the single source of truth for valid category/service/subservice values —
  no per-category if/elif chains anywhere else in the codebase (NFR-MAINT-01).
- If `support/v1/services`/`support/v1/pay-transfer` turn out to need their own auth this system
  doesn't yet have, stop and report back to architect rather than guessing a credential — this is
  a flagged open item (SRS Appendix B item 6), not something to silently work around.

If a task needs a new setting in `app/config.py` (e.g. the platform's base URL, refresh interval),
add it there directly — that file is shared across segments, not exclusively owned by this one;
keep the addition to exactly what this task needs.

## Test command
`docker compose exec -T backend python -m pytest -q -k taxonomy`
