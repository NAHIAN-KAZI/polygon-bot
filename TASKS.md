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
| 4 | Implement periodic taxonomy refresh + cache-fallback on failure [E-03/F-02], T-04 (revised 2026-09-01) — folded into T-03's implementation, verified covered by test_taxonomy.py (no separate work needed) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ✅ DONE | banking-service-catalog | 2026-09-01 | 2026-09-01 |
| 5 | Implement pluggable JWT verification interface + fail-closed stub [E-03/F-03], T-05 | Establish foundation for future change | Planning 2026-08-31 | 🔴 | — | ✅ DONE | customer-identity-session | 2026-09-01 | 2026-09-01 |
| 6 | Implement AUTH_REQUIRED handling for missing/invalid JWT [E-03/F-03], T-06 | Establish foundation for future change | Planning 2026-08-31 | 🔴 | — | ✅ DONE | customer-identity-session | 2026-09-01 | 2026-09-01 |
| 7 | Implement in-memory session store (get/set/expire, 30-min TTL) [E-03/F-04], T-07 | Establish foundation for future change | Planning 2026-08-31 | 🔴 | — | ✅ DONE | customer-identity-session | 2026-09-01 | 2026-09-01 |
| 8 | Define common banking-service adapter interface incl. JWT pass-through param [E-03/F-05], T-08 (revised 2026-09-01) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ✅ DONE | banking-service-integration | 2026-09-01 | 2026-09-01 |
| 9 | Implement mock adapters for all non-real subservices + taxonomy-to-adapter wiring [E-03/F-02,F-05], T-09 (revised 2026-09-01) — found+fixed a label bug in get_adapter_name during review (subservice_id wasn't prioritized over service_id in the "real:" label) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ✅ DONE | swarm:adapter-taxonomy-wiring | 2026-09-01 | 2026-09-01 |
| 10 | Implement SERVICE_UNAVAILABLE/AUTH_REQUIRED branching for adapter failure (real+mock) [E-03/F-05], T-10 (revised 2026-09-01) — built adapter resolver (get_adapter, fulfill_banking_service) tying adapter_map names to real/mock instances; exceptions propagate uncaught for T-15 to translate into response types; verified live end-to-end | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ✅ DONE | banking-service-integration | 2026-09-01 | 2026-09-01 |
| 11 | Spike: verify qwen3:8b tool-calling reliability via Ollama /api/chat [E-01/F-01], T-11 — RESULT: works reliably but ONLY with a carefully engineered system prompt (explicit numbered decision rules + concrete examples + "when in doubt, ask_clarification, never guess" instruction). A minimal/naive prompt reliably misclassified both the KB-question and ambiguous-request test cases, defaulting to route_banking_service and guessing values every time — this is the exact failure FR-ROUTE-03 exists to prevent. T-12 MUST use the engineered-prompt pattern, not a minimal one. Verified live against gpu-vm-01's Ollama (also caught+fixed a recurring GPU-discovery-stall CPU-fallback issue mid-spike via `docker restart ollama`) | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ✅ DONE | conversation-routing | 2026-09-01 | 2026-09-01 |
| 12 | Implement classification call + branching (KB/banking-service/clarification) [E-01/F-01], T-12 — found+documented (ADR-0004): requires think=true, not think=false as originally assumed; empty-string subservice from Ollama normalized to None | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ✅ DONE | conversation-routing | 2026-09-01 | 2026-09-01 |
| 13 | Implement UNKNOWN_SERVICE handling for out-of-taxonomy classification [E-01/F-01], T-13 — folded into T-12's implementation (UnknownService type + is_valid_path check), verified covered by test_routing.py (no separate work needed) | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ✅ DONE | conversation-routing | 2026-09-01 | 2026-09-01 |
| 14 | Extend ChatRequest with optional category/service/subservice/payload [E-01/F-06], T-14 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ✅ DONE | chat-api-contract | 2026-09-01 | 2026-09-01 |
| 15 | Implement result SSE event for all non-KB outcomes, incl. real-adapter data in reply/payload [E-01/F-06], T-15 (revised 2026-09-01) — wired classify/is_valid_path/identity/adapters into chat.py; 5 result types (BANKING_SERVICE/CLARIFICATION_REQUIRED/AUTH_REQUIRED/UNKNOWN_SERVICE/SERVICE_UNAVAILABLE); INTEGRATION.md updated; gate: 142 passed, live health ok | Recognize banking-service requests and route them | Planning 2026-09-01 | 🔴 | — | ✅ DONE | chat-api-contract | 2026-09-01 | 2026-09-02 |
| 16 | Implement structured audit log line per banking-service turn [E-01/F-07], T-16 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | security-compliance | — | — |
| 17 | Regression-test extended /chat contract against INTEGRATION.md [E-01/F-06], T-17 | Recognize banking-service requests and route them | Planning 2026-08-31 | 🔴 | — | ⏳ TODO | chat-api-contract | — | — |
| 18 | Add type/category/service/subservice/payload/routing display to demo frontend [E-04/F-08], T-18 | Keep new behavior easy to verify | Planning 2026-08-31 | 🟡 | — | ⏳ TODO | kb-chat-preserved | — | — |
| 19 | Implement 5 real adapters (balance, transaction history, accounts, device history, login history) forwarding JWT to platform endpoints [E-03/F-05], T-19 (added 2026-09-01) — swarm: synthetic taxonomy entries (banking-service-catalog, ADR-0011 amended) + real HTTP adapters (banking-service-integration); verified live against dev platform: all 5 correctly raise AdapterAuthError on 401 (no real customer JWT available to test success path) | Establish foundation for future change | Planning 2026-09-01 | 🔴 | — | ✅ DONE | swarm:real-adapters | 2026-09-01 | 2026-09-01 |

## Completed Tasks

_(none yet)_

## Manager Run History

_(none yet)_
