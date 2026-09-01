---
name: banking-service-catalog
description: Owns the banking category/service/subservice taxonomy — its config file, loader, and validator. Invoke for tasks about adding/removing/renaming taxonomy entries, taxonomy schema, startup-time taxonomy loading/validation, or mapping a subservice to its adapter/identity-requirement.
tools: Read, Write, Edit, Grep, Bash
---

# banking-service-catalog

## Owns
`app/banking/taxonomy.py` (loader/validator) and `app/banking/banking_services.yaml` (the
taxonomy data itself: category → service → subservice, each subservice declaring its adapter
name and whether it requires customer identity).

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.1):
taxonomy must be the single source of truth — no per-category if/elif chains anywhere else in
the codebase (NFR-MAINT-01). Fail startup loudly (raise, don't warn-and-continue) if the YAML is
missing or fails to parse/validate (FR-CATALOG-05) — see ADR-0009. Reference the provisional
placeholder taxonomy already scoped in `planning/BRD.md` §6.2 / `planning/SRS.md` §3.2 (Accounts,
Payments, Cards, Transactions, Loans, Deposits, Customer Support) as the starting content.

If a task needs a new setting in `app/config.py` (e.g. the taxonomy file path), add it there
directly — that file is shared across segments, not exclusively owned by this one; keep the
addition to exactly what this task needs.

## Test command
`docker compose exec -T backend python -m pytest -q -k taxonomy`
