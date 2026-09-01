---
name: banking-service-integration
description: Owns the banking-service adapter interface and both its real and mock implementations. Invoke for tasks about calling out to fulfill a banking-service request, the 5 real adapters (balance/transactions/accounts/device-history/login-history) forwarding a customer's JWT, mock/canned data for every other subservice, or adapter failure/timeout/auth-error handling.
tools: Read, Write, Edit, Grep, Bash
---

# banking-service-integration

## Owns
`app/banking/adapters/` — the common `fulfill(customer_identity, jwt, subservice, payload) ->
result` interface, real adapter implementations for the 5 subservices with a known live endpoint,
and mock implementations for every other subservice.

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.2,
`planning/SRS.md` v0.2 §3.4, ADR-0010, ADR-0012, ADR-0014):

- **Real adapters (5 only)** — balance (`POST transfer/v1/accounting/balance`), transaction
  history (`GET transfer/v1/accounting/transaction-list`), accounts
  (`GET polygon-bank/v1/accounts{/id}`), device history (`GET auth/v1/devices`), login history
  (`GET auth/v1/devices/{id}/login-history`). Forward the customer's verified JWT as-is
  (`Authorization: Bearer <JWT>`) — do not mint a separate token or invent credentials. This
  pass-through assumption is unconfirmed (ADR-0014) — if it visibly fails against a real token
  during testing, stop and report back to architect rather than working around it silently.
- **Mock adapters (everything else)** — return realistic, clearly-fake canned data (FR-INTEG-02)
  — never invent real banking API URLs or credentials for subservices without a documented
  endpoint (BRD §4.2 out of scope).
- A real adapter never falls back to mock data on failure. Distinguish failure types: a
  downstream 401/403 becomes `AUTH_REQUIRED` (the customer's JWT was rejected — FR-INTEG-06);
  any other failure/timeout becomes `SERVICE_UNAVAILABLE` (FR-INTEG-04). Never swallow errors
  silently or leak internal exception detail up to the API response — full detail belongs only
  in the audit log (`security-compliance` segment).
- Design the interface generically enough that a mock can be replaced by a real adapter later
  (for a currently-mocked subservice) without changing routing/classification or the chat
  contract (FR-INTEG-03).

## Test command
`docker compose exec -T backend python -m pytest -q -k adapter`
