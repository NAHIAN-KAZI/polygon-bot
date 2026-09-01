# Epics

## Polygon Bot — Banking Intent & Service Routing

| | |
|---|---|
| **Document title** | Polygon Bot — Epics |
| **Version** | 0.1 |
| **Date** | 2026-08-31 |
| **Based on** | FEATURES v0.1, ADRs 0001–0010 |
| **Status** | Approved |

---

## Delivery plan

**Mode:** Whole project at once.

Epics run in this order — WSJF-ranked, then re-sequenced where a hard dependency overrides pure
score (E-04 scores above E-01/E-03 on WSJF alone, but depends on E-01's output; E-01 depends on
E-03's foundation):

1. **E-02** — Existing KB chat keeps working (WSJF 7.0, no dependencies — regression safety net goes in first)
2. **E-03** — Foundation for future change (WSJF 2.6, no dependencies — must exist before E-01 can be built)
3. **E-01** ★ — Recognize and route banking-service requests (WSJF 2.9, depends on E-03)
4. **E-04** — Verify routing behavior in the demo frontend (WSJF 4.0, depends on E-01)

## E-01 — Customers get routed straight to the banking feature they asked for ★

**When this ships:** a bank customer asking Polygon Bot something like "what's my balance" or "I
want to send money" gets recognized and routed to the right feature, with the main Polygon Bank
app able to take them straight there — instead of the request being (incorrectly) answered as a
knowledge-base question or landing nowhere.

**Goal:** → "Recognize banking-service requests and return structured routing information"

**WSJF:** (value 10 + time-criticality 7 + risk-reduction 6) / size 8 = **2.9**

### Scope

**In scope**
- Classifying a message as KB question, banking-service request, or ambiguous, via one Ollama
  tool-calling call.
- Extending the `/chat` request/response contract with the new optional fields and the `result`
  SSE event.
- Structured audit logging for every banking-service turn.
- `UNKNOWN_SERVICE` and `AUTH_REQUIRED` outcome handling as part of the routing flow.

**Out of scope**
- The taxonomy itself, JWT verification, session storage, and mock adapters — built in E-03, this
  epic consumes them (deferred to E-03).
- Demo frontend display of the new fields (deferred to E-04).

### Acceptance criteria (EARS)

- **EARS-ROUTE-1**: WHEN a `/chat` message is a knowledge-base question, the system SHALL answer
  it via the existing, unmodified RAG flow (FR-ROUTE-02).
- **EARS-ROUTE-2**: WHEN a `/chat` message is a banking-service request with a resolvable
  category/service/subservice, the system SHALL emit a `result` event with `type:
  BANKING_SERVICE` and routing information (FR-ROUTE-01, FR-CONTRACT-03/05).
- **EARS-ROUTE-3**: WHEN a `/chat` message is genuinely ambiguous, the system SHALL stream a
  clarifying question and emit `type: CLARIFICATION_REQUIRED`, never guessing a subservice
  (FR-ROUTE-03).
- **EARS-ROUTE-4**: IF a banking-service request arrives without a valid customer identity JWT,
  THEN the system SHALL emit `type: AUTH_REQUIRED` and not proceed to adapter fulfillment
  (FR-IDENT-04).
- **EARS-ROUTE-5**: IF a classified category/service/subservice isn't a valid taxonomy path, THEN
  the system SHALL emit `type: UNKNOWN_SERVICE` (FR-ROUTE-05 business rule).
- **EARS-ROUTE-6**: WHEN a request contains only `message`, the system SHALL behave identically to
  today's `/chat` contract — no `result` event, same `token`/`done`/`error` sequence
  (FR-CONTRACT-02).
- **EARS-ROUTE-7**: WHEN a banking-service turn completes (any outcome), the system SHALL emit one
  structured audit log line with no raw JWT/API key/secret content (FR-SEC-03/04).

### Tasks

| Task | Description | Size | MoSCoW | Depends on | Traces to |
|---|---|---|---|---|---|
| T-11 | Spike: verify `qwen3:8b` tool-calling reliability via Ollama `/api/chat` with the 3-tool schema | S | Must | T-04 | FR-ROUTE-01/05, F-01 |
| T-12 | Implement classification call + branching (KB / banking-service / clarification paths) | L | Must | T-11, T-07 | FR-ROUTE-01..04, NFR-PERF-01, F-01 |
| T-13 | Implement `UNKNOWN_SERVICE` handling for an out-of-taxonomy classification | XS | Must | T-04, T-12 | FR-ROUTE-05, F-01 |
| T-14 | Extend `ChatRequest` with optional `category`/`service`/`subservice`/`payload`; `message` unchanged, `session_id` accepted-but-ignored | XS | Must | — | FR-CONTRACT-01, F-06 |
| T-15 | Implement `result` SSE event (all non-KB outcome types) after `token` events, before `done` | M | Must | T-12, T-06, T-10, T-13 | FR-CONTRACT-02..06, F-06 |
| T-16 | Implement structured audit log line per banking-service turn, excluding secrets/PII | S | Must | T-15 | FR-SEC-01..04, NFR-SEC-02, NFR-OBS-01, F-07 |
| T-17 | Regression-test extended `/chat` contract against `INTEGRATION.md` (text-only requests unaffected) | S | Must | T-15 | FR-CONTRACT-02, F-06 |

### Risks

| Risk | Mitigation |
|---|---|
| `qwen3:8b` tool-calling via `/api/chat` may not be reliable enough for production classification | T-11 spikes this first, before any other E-01 task is built on top of it (ADR-0004) |
| New `result` event accidentally breaks the existing SSE contract for the current integration team | T-17 regression-tests explicitly against `INTEGRATION.md`, not just new-behavior tests |

## E-02 — Existing knowledge-base chat keeps working exactly as before

**When this ships:** the existing external integration team's KB chat integration continues
working exactly as documented in `INTEGRATION.md`, with zero required changes on their end,
throughout and after this entire extension.

**Goal:** → "Preserve all existing knowledge-base chat behavior and its API contract exactly as-is"

**WSJF:** (value 8 + time-criticality 8 + risk-reduction 5) / size 3 = **7.0**

### Scope

**In scope**
- A regression test suite covering today's `/chat` and `/documents` behavior, run before and
  after every other epic's work lands.
- Confirming `app/chunking.py`, `app/embeddings.py`, `app/vectorstore.py` receive no functional
  changes.

**Out of scope**
- Any new functionality — this epic is purely a safety net around what already exists.

### Acceptance criteria (EARS)

- **EARS-KB-1**: WHEN a `/chat` request contains only `message`, the system SHALL return the same
  event sequence and answer behavior as today's documented contract (FR-KB-01, FR-CONTRACT-02).
- **EARS-KB-2**: WHEN `/documents` upload/list/delete is exercised, the system SHALL behave
  identically to today, with no functional change to chunking, embeddings, or vector storage
  (FR-KB-01).

### Tasks

| Task | Description | Size | MoSCoW | Depends on | Traces to |
|---|---|---|---|---|---|
| T-01 | Write regression test suite for existing `/chat`/`/documents` behavior against current `INTEGRATION.md` contract | S | Must | — | FR-KB-01, F-08 |
| T-02 | Re-run regression suite (T-01) after each subsequent epic lands; treat any failure as a blocker | XS | Must | T-01 | FR-KB-01, F-08 |

### Risks

| Risk | Mitigation |
|---|---|
| No test suite exists in the repo today (confirmed by codebase-analyst) — this is the first one | T-01 establishes the baseline before any other epic touches shared code paths |

## E-03 — The system can absorb new banking categories, real APIs, and real identity later without a redesign

**When this ships:** the Polygon Bot owner can add, remove, or reconfigure banking
categories/services/subservices, and later swap in the bank's real customer-identity tokens and
real banking APIs, without any engineer redesigning the chatbot's core logic.

**Goal:** → "Establish a foundation that absorbs future taxonomy/API/identity changes without a redesign"

**WSJF:** (value 7 + time-criticality 4 + risk-reduction 7) / size 7 = **2.6**

### Scope

**In scope**
- The taxonomy config file and loader.
- Pluggable, fail-closed JWT verification.
- In-memory session store behind a swappable interface.
- Common banking-service adapter interface with mock implementations.

**Out of scope**
- The official taxonomy, real JWT signing details, and real banking APIs themselves — all
  explicitly pending external inputs (BRD Open Items 1–3), not built here.

### Acceptance criteria (EARS)

- **EARS-FOUND-1**: WHEN the service starts, the system SHALL load and validate
  `banking_services.yaml`, failing startup loudly if it's missing or invalid (FR-CATALOG-05).
- **EARS-FOUND-2**: WHERE a category/service/subservice is added, removed, or renamed in
  `banking_services.yaml`, the system SHALL reflect that after a restart with no code change
  elsewhere (FR-CATALOG-03).
- **EARS-FOUND-3**: WHEN a JWT is presented, the system SHALL verify it via a pluggable function
  and SHALL treat any unverifiable token as unauthenticated (fail closed) (FR-IDENT-01,
  NFR-SEC-01).
- **EARS-FOUND-4**: WHEN 30 minutes pass with no activity for a customer's session, the system
  SHALL treat the next message as starting a fresh session with no prior context (FR-IDENT-05).
- **EARS-FOUND-5**: WHEN a banking-service adapter is invoked and fails or times out, the system
  SHALL surface `SERVICE_UNAVAILABLE` without exposing internal error detail (FR-INTEG-04).

### Tasks

| Task | Description | Size | MoSCoW | Depends on | Traces to |
|---|---|---|---|---|---|
| T-03 | Define `banking_services.yaml` schema; write the provisional placeholder taxonomy | S | Must | — | FR-CATALOG-02, F-02 |
| T-04 | Implement taxonomy loader/validator (startup load, fail loudly) | S | Must | T-03 | FR-CATALOG-01/03/05, F-02 |
| T-05 | Implement pluggable JWT verification interface + fail-closed stub | M | Must | — | FR-IDENT-01/02/04, NFR-SEC-01, F-03 |
| T-06 | Implement `AUTH_REQUIRED` handling for missing/invalid JWT on a banking-eligible request | S | Must | T-05 | FR-IDENT-04, F-03 |
| T-07 | Implement in-memory session store (get/set/expire, 30-min TTL, capped turns) keyed by JWT subject | M | Must | T-05 | FR-IDENT-05..07, F-04 |
| T-08 | Define common banking-service adapter interface | S | Must | — | FR-INTEG-01/03, F-05 |
| T-09 | Implement mock adapters per subservice; wire taxonomy-to-adapter mapping | M | Must | T-03, T-08 | FR-INTEG-02, FR-CATALOG-04, F-02, F-05 |
| T-10 | Implement `SERVICE_UNAVAILABLE` handling for adapter failure/timeout | S | Must | T-09 | FR-INTEG-04, NFR-REL-01, F-05 |

### Risks

| Risk | Mitigation |
|---|---|
| Real JWT signing details may arrive with a shape that doesn't fit the assumed interface | T-05's interface is deliberately minimal (`verify(token) -> identity | None`) to absorb surprises |

## E-04 — The Polygon Bot owner can verify routing behavior directly in the demo frontend

**When this ships:** the Polygon Bot owner can see exactly how each test message was classified
and routed — type, category, service, subservice, payload, routing — directly in the demo
frontend, without inspecting raw API responses.

**Goal:** → "Keep the new behavior easy to verify via the existing demo/test frontend"

**WSJF:** (value 4 + time-criticality 2 + risk-reduction 2) / size 2 = **4.0**

### Scope

**In scope**
- Displaying the `result` event's contents in the existing demo frontend chat UI.

**Out of scope**
- Any production-facing UI — this is dev/test tooling only (BRD §4.2).

### Acceptance criteria (EARS)

- **EARS-DEMO-1**: WHEN a `result` event arrives, the demo frontend SHALL display its type,
  category, service, subservice, payload, and routing fields alongside the chat reply
  (FR-KB-02).

### Tasks

| Task | Description | Size | MoSCoW | Depends on | Traces to |
|---|---|---|---|---|---|
| T-18 | Add type/category/service/subservice/payload/routing display to the demo frontend, parsing the new `result` event | S | Should | T-15 | FR-KB-02, F-08 |

### Risks

| Risk | Mitigation |
|---|---|
| None significant — small, isolated frontend addition | — |

## Coverage check

Every Feature/FR from `planning/FEATURES.md` lands in exactly one epic:

- F-01 (FR-ROUTE-01..05) → E-01
- F-02 (FR-CATALOG-01..05) → E-03
- F-03 (FR-IDENT-01..04) → E-03
- F-04 (FR-IDENT-05..07) → E-03
- F-05 (FR-INTEG-01..04) → E-03
- F-06 (FR-CONTRACT-01..06) → E-01
- F-07 (FR-SEC-01..04) → E-01
- F-08 (FR-KB-01 → E-02; FR-KB-02 → E-04 — the one Feature split across two epics at the FR level, both of its FRs each landing in exactly one epic, per its own dual concern of "preserve existing behavior" + "add test-visibility tooling")

No orphans, no duplicates.

## Open Items (TBD)

1. Exact audit log destination/format (carried from SRS/Features) — doesn't block T-16, assumed stdout structured JSON for now. (§E-01)

---
*End of document — v0.1, Approved 2026-08-31. Open items: 1, non-blocking.*
