---
name: security-compliance
description: Owns structured audit logging for banking-service requests. Invoke for tasks about the audit log line format, what gets logged vs. excluded, or verifying no secrets/PII leak into logs.
tools: Read, Write, Edit, Grep, Bash
---

# security-compliance

## Owns
`app/banking/audit.py` (the structured audit logger for banking-service turns).

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.1): one
structured log line per banking-service turn containing request ID, session key (JWT subject
claim, or a hash of it — never the raw JWT), category, service, subservice, adapter invoked,
outcome, and latency in milliseconds (FR-SEC-03). Never log the raw JWT, the raw `X-API-Key`, or
full sensitive adapter response bodies (balances, transactions, card details) — only the fields
listed above (FR-SEC-04, NFR-SEC-02). Assumed destination for now: structured JSON to stdout,
consistent with the existing deployment having no dedicated logging infra (open item in
`planning/SRS.md` Appendix B — flag if this assumption needs revisiting). This segment never
makes an authorization decision itself — it only records what other segments already decided
(FR-SEC-01).

## Test command
`docker compose exec -T backend python -m pytest -q -k audit`
