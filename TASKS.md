# Tasks

> Single source of truth for all agentic work in this repo. `/agentic-harness:architect` reads
> this before planning; `/agentic-harness:manager` and `/agentic-harness:epics` append new
> tasks here — every task must cite the business goal (from `planning/BUSINESS_GOALS.md`) it
> serves, and, if it came from the planning phase, its `[E-##/F-##]` trace tag; a task serving
> no goal doesn't get queued without an explicit reason. Any enabled tool-mirror skill (see
> `planning/project.config.yaml`'s `tools:` block, e.g. `/agentic-harness:clickup-log`) mirrors
> every write to the external tracker, scoped to rows dated `tools.<name>.mirror_from_date`
> onward — no backfill.

_Last updated: 2026-09-01_

## Status legend
⏳ TODO · 🔄 IN_PROGRESS · ✅ DONE (tests passing) · ⚠ BLOCKED · ❌ FAILED

A task only reaches ✅ DONE once its tests pass — see `architect.md` Phase 3.

## Source convention
`Manager YYYY-MM-DD` (from /agentic-harness:manager) · `Planning YYYY-MM-DD` (seeded by /agentic-harness:epics) · `User YYYY-MM-DD` (direct ask) · `Auto YYYY-MM-DD` (self-queued)

## Priority
🔴 FAIL-level / urgent · 🟡 WARNING-level / soon · 🟢 nice-to-have

## Sprint
Only meaningful if `planning.delivery_mode: sprint_weekly` (see
`planning/project.config.yaml`); a task's epic's assigned sprint number, or
`—` if this project delivers as a whole (`single_batch`) or the row didn't
come from planning. `/agentic-harness:architect` defaults its execution
scope to the active sprint when this column is in use.

| # | Task | Goal | Source | Priority | Sprint | Status | Agent | Started | Completed |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Write regression test suite for existing /chat and /documents behavior vs INTEGRATION.md [E-02/F-08], T-01 | Preserve existing KB chat behavior | Planning 2026-08-31 | 🔴 | — | ✅ DONE | kb-chat-preserved | 2026-09-01 | 2026-09-01 |
| 2 | Re-run regression suite after each subsequent epic lands [E-02/F-08], T-02 | Preserve existing KB chat behavior | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | kb-chat-preserved | — | — |
| 3 | Implement live taxonomy fetcher: merge support/v1/services + support/v1/pay-transfer, retain platform ids [E-03/F-02], T-03 (revised 2026-09-01) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ✅ DONE | banking-service-catalog | 2026-09-01 | 2026-09-01 |
| 4 | Implement periodic taxonomy refresh + cache-fallback on failure [E-03/F-02], T-04 (revised 2026-09-01) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ⏳ TODO | banking-service-catalog | — | — |
| 5 | Implement pluggable JWT verification interface + fail-closed stub [E-03/F-03], T-05 | Establish foundation for future change | Planning 2026-08-31 | 🔴 | — | ✅ DONE | customer-identity-session | 2026-09-01 | 2026-09-01 |
| 6 | Implement AUTH_REQUIRED handling for missing/invalid JWT [E-03/F-03], T-06 | Establish foundation for future change | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | customer-identity-session | — | — |
| 7 | Implement in-memory session store (get/set/expire, 30-min TTL) [E-03/F-04], T-07 | Establish foundation for future change | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | customer-identity-session | — | — |
| 8 | Define common banking-service adapter interface incl. JWT pass-through param [E-03/F-05], T-08 (revised 2026-09-01) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ⏳ TODO | banking-service-integration | — | — |
| 9 | Implement mock adapters for all non-real subservices + taxonomy-to-adapter wiring [E-03/F-02,F-05], T-09 (revised 2026-09-01) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ⏳ TODO | swarm:adapter-taxonomy-wiring | — | — |
| 10 | Implement SERVICE_UNAVAILABLE/AUTH_REQUIRED branching for adapter failure (real+mock) [E-03/F-05], T-10 (revised 2026-09-01) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ⏳ TODO | banking-service-integration | — | — |
| 11 | Spike: verify qwen3:8b tool-calling reliability via Ollama /api/chat [E-01/F-01], T-11 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | conversation-routing | — | — |
| 12 | Implement classification call + branching (KB/banking-service/clarification) [E-01/F-01], T-12 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | conversation-routing | — | — |
| 13 | Implement UNKNOWN_SERVICE handling for out-of-taxonomy classification [E-01/F-01], T-13 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | conversation-routing | — | — |
| 14 | Extend ChatRequest with optional category/service/subservice/payload [E-01/F-06], T-14 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | chat-api-contract | — | — |
| 15 | Implement result SSE event for all non-KB outcomes, incl. real-adapter data in reply/payload [E-01/F-06], T-15 (revised 2026-09-01) | Recognize banking-service requests and route them | Planning 2026-09-01 | 🔴 | — | ⏳ TODO | chat-api-contract | — | — |
| 16 | Implement structured audit log line per banking-service turn [E-01/F-07], T-16 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | security-compliance | — | — |
| 17 | Regression-test extended /chat contract against INTEGRATION.md [E-01/F-06], T-17 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | chat-api-contract | — | — |
| 18 | Add type/category/service/subservice/payload/routing display to demo frontend [E-04/F-08], T-18 | Keep new behavior easy to verify | Planning 2026-08-31 | 🟡 | — | ⏳ TODO | kb-chat-preserved | — | — |
| 19 | Implement 5 real adapters (balance, transaction history, accounts, device history, login history) forwarding JWT to platform endpoints [E-03/F-05], T-19 (added 2026-09-01) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ⏳ TODO | banking-service-integration | — | — |

## Completed Tasks

_(none yet)_

## Manager Run History

_(none yet)_
