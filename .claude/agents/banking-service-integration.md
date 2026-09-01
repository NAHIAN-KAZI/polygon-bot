---
name: banking-service-integration
description: Owns the banking-service adapter interface and its mock implementations. Invoke for tasks about calling out to fulfill a banking-service request, mock/canned data per subservice, adapter failure/timeout handling, or replacing a mock with a real integration later.
tools: Read, Write, Edit, Grep, Bash
---

# banking-service-integration

## Owns
`app/banking/adapters/` (the common `fulfill(customer_identity, subservice, payload) -> result`
interface, plus one mock implementation per subservice).

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.1): mock
adapters return realistic, clearly-fake canned data (FR-INTEG-02) — never invent real banking API
URLs or credentials (BRD §4.2 out of scope). Design the interface generically enough that a real
adapter drops in later without changing routing/classification or the chat contract (FR-INTEG-03,
ADR-0010). On adapter failure/timeout, raise a typed exception the caller turns into
`SERVICE_UNAVAILABLE` — do not swallow errors silently or leak internal exception detail up to
the API response (FR-INTEG-04); full detail belongs only in the audit log
(`security-compliance` segment).

## Test command
`docker compose exec -T backend python -m pytest -q -k adapter`
