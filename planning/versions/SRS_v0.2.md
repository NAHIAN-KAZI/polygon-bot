# Software Requirements Specification

## Polygon Bot — Banking Intent & Service Routing

| | |
|---|---|
| **Document title** | Polygon Bot — Software Requirements Specification |
| **Version** | 0.2 |
| **Date** | 2026-09-01 |
| **Author** | Nahian Kazi |
| **Based on** | Polygon Bot BRD v0.2 |
| **Status** | Approved |

## 1. Introduction

### 1.1 Purpose

Elaborates `planning/BRD.md` v0.1's business requirements into concrete, testable system
behavior: exact request/response shapes, the classification mechanism, session and identity
handling, the banking-service taxonomy format, the mock-to-real integration boundary, and
observability requirements — enough detail to implement against directly.

### 1.2 Document Conventions

Requirement IDs carry a module prefix inherited from the BRD (`FR-<MODULE>-##`). IDs already
defined in the BRD are elaborated here with the same ID; new IDs continue that module's numeric
sequence for behavior the BRD didn't itemize individually. Priority: **M** (Must-have), **S**
(Should-have), **C** (Could-have) — inherited from the BRD unless stated otherwise. Requirement
phrasing follows "the system shall...".

### 1.3 Intended Audience

The engineer(s) implementing this extension (primarily the Polygon Bot owner), and — for
Appendix A (Traceability) and §5 (External Interface Requirements) specifically — the main
Polygon Bank application team, who need the exact contract they're integrating against.

### 1.4 Product Scope

Same boundary as BRD §4: Polygon Bot classifies chat messages, answers knowledge-base questions
via its existing RAG pipeline unchanged, and — for banking-service requests — identifies a
category/service/subservice and returns structured routing/result information. It does not
execute banking transactions, does not own customer identity/login, and does not build
destination pages.

### 1.5 Definitions, Acronyms, Abbreviations

| Term | Meaning |
|---|---|
| SSE | Server-Sent Events — the streaming transport `/chat` already uses for token-by-token answers. |
| JWT | JSON Web Token — the customer identity token issued by the main Polygon Bank application. |
| Taxonomy | The category → service → subservice tree Polygon Bot classifies banking requests against. |
| Tool call | An Ollama `/api/chat` response where the model selects a defined function/tool instead of (or alongside) free text, used here for classification. |
| Session | A customer's ongoing conversation context, keyed by their JWT identity, held in memory for a rolling 30-minute idle window. |

### 1.6 References

- `planning/BRD.md` v0.2 (approved 2026-09-01)
- `INTEGRATION.md` (existing `/chat`/`/documents` contract documentation, current consuming team)
- `user-app-api-map.md` (the main mobile application's real endpoint/navigation reference,
  provided 2026-09-01 by the frontend/backend team — source for §3.2's live taxonomy fetch,
  §3.4's real-adapter subset, and §3.5's routing identifier format)

## 2. Overall Description

### 2.1 Product Perspective

Polygon Bot remains a standalone FastAPI service (unchanged: Qdrant for vectors, Ollama for
`qwen3:8b` generation and `all-minilm` embeddings). This extension adds an intent-classification
step ahead of the existing RAG path, a taxonomy-driven routing layer, JWT-based identity
attachment, an in-memory session store, and a mock/real banking-service integration boundary. No
existing component (chunking, embeddings, vector store, document catalog) is replaced.

### 2.2 Product Functions (summary)

- Classify each `/chat` message: KB question, banking-service request, or ambiguous.
- For KB questions: unchanged existing RAG behavior.
- For banking-service requests: identify category/service/subservice (or ask a clarifying
  question), call the (mocked, for now) banking-service integration, and return a structured
  result alongside a natural-language reply.
- Attach a verified customer identity (from JWT) to banking-service requests; reject with a
  structured auth-required response when identity can't be verified.
- Retain per-customer session context for a 30-minute idle window.

### 2.3 User Classes and Characteristics

| Class | Characteristics |
|---|---|
| Bank customer (via main app) | Sends messages through the main Polygon Bank application, which attaches their JWT. Never calls Polygon Bot directly. |
| Main Polygon Bank application | Machine client. Sends `Authorization: Bearer <JWT>` on behalf of an authenticated customer; consumes the `result` SSE event to navigate the customer. |
| Existing external integration team | Machine client, KB-only usage, authenticates via the existing shared `X-API-Key`, never sends a JWT. Must see zero behavior change. |
| Polygon Bot owner | Uses the demo frontend directly; sees the new classification/routing detail surfaced for testing. |

### 2.4 Operating Environment

Unchanged: single FastAPI/uvicorn process (Docker container), Qdrant (separate container, same
compose stack), Ollama (external container on the host, GPU-pinned, reached via
`host.docker.internal`). The in-memory session store (§3.3) lives in this same single process —
consistent with the current single-worker deployment; BRD FR-IDENT-06 explicitly defers a shared
store to later.

### 2.5 Design and Implementation Constraints

- No new external infrastructure this phase (no Redis/DB for sessions — in-memory only, per
  BRD FR-IDENT-06 and the user's explicit "for demo do in-memory, for future we manage" answer).
- JWT verification must be pluggable: the actual issuer/algorithm/signing-key details are not yet
  available (BRD Open Item 1) — the verification function must be swappable without touching
  call sites once real values arrive.
- No real banking-service credentials or URLs may be hardcoded (BRD §4.2, out of scope).
- Must not modify `app/chunking.py`, `app/embeddings.py`, or `app/vectorstore.py` — the existing
  RAG pipeline is out of scope for changes (BRD FR-KB-01).

### 2.6 Assumptions and Dependencies

- `qwen3:8b` in Ollama supports tool/function calling via `/api/chat` (the classification
  mechanism in §3.1 depends on this — if a spike shows otherwise, this section needs revisiting
  before implementation proceeds past a prototype).
- The existing `X-API-Key` check remains the outer gate for every `/chat`/`/documents` call
  exactly as today; JWT is an additional, independent identity layer checked only for
  banking-service requests, not a replacement for the API key.
- *(Added 2026-09-01)* The main platform's `support/v1/services` and `support/v1/pay-transfer`
  endpoints (per `user-app-api-map.md`) are reachable from Polygon Bot's deployment environment,
  and returning the same catalog shape the mobile app already consumes (categories → services →
  optional subServices, each with an `id`, `isActive`, and — for pay-transfer — an `action`
  object). If these endpoints require their own auth Polygon Bot doesn't yet hold, that's a
  blocker for §3.2 and needs resolving before implementation, not silently worked around.
- *(Added 2026-09-01)* The customer's JWT, once the main application team supplies it, is
  forwardable as-is (`Authorization: Bearer <JWT>`) to the five real banking-service endpoints
  named in §3.4 — i.e. it is accepted by those same downstream services via Kong, not a
  Polygon-Bot-specific token requiring translation. This is not yet confirmed (BRD Open Item 1
  still covers the exact JWT specifics) — §3.4's real adapters are built against this assumption
  and must be revisited if it proves false.

## 3. System Features (Functional Requirements)

### 3.1 Conversation Routing

Priority: M · Actors: any `/chat` caller · Precondition: `X-API-Key` already validated (existing
behavior, unchanged).

**Primary flow:**
1. `/chat` receives a message (plus optional `category`/`service`/`subservice`/`payload`).
2. If `category`, `service`, and `subservice` are all already supplied by the caller, skip
   classification entirely and go straight to §3.4 (Banking Service Integration).
3. Otherwise, call Ollama's `/api/chat` with `qwen3:8b`, the conversation's recent turns (§3.3),
   and a tool schema describing: `answer_kb_question` (no args — signals a KB question, existing
   RAG path handles it), `route_banking_service(category, service, subservice)` (signals a
   banking-service request with the model's best-guess classification, constrained to values
   present in the taxonomy, §3.2), and `ask_clarification(question)` (signals genuine ambiguity).
4. On `answer_kb_question` (or no tool call at all): existing RAG flow, unchanged.
5. On `route_banking_service`: proceed to §3.4 with the model's category/service/subservice.
6. On `ask_clarification`: stream the model's clarifying question as the reply; no `result` event
   is emitted (nothing to route yet) beyond `type: CLARIFICATION_REQUIRED` (§3.5).

| ID | Requirement | Priority |
|---|---|---|
| FR-ROUTE-01 | The system shall classify each message as `KB_INFORMATION`, `BANKING_SERVICE`, or `CLARIFICATION_REQUIRED` via a single Ollama `/api/chat` tool-calling request, before any RAG retrieval happens for that turn. | M |
| FR-ROUTE-02 | KB-classified messages shall be answered via the existing, unmodified RAG flow (retrieval → prompt → `/api/generate` streaming). | M |
| FR-ROUTE-03 | When the model calls `ask_clarification`, the system shall stream its clarifying question as the reply and shall not call the banking-service integration or return routing information for that turn. | M |
| FR-ROUTE-04 | If the caller supplies `category`, `service`, and `subservice` directly in the request, the system shall skip classification and route directly, still validating the triple against the current taxonomy (§3.2) before proceeding. | M |
| FR-ROUTE-05 | The tool schema offered to the model shall only ever expose category/service/subservice values that currently exist in the taxonomy (§3.2) — the model must not be able to select or invent a value outside it. | M |

*Business rules / errors:* if the model's tool call returns a category/service/subservice
combination that isn't a valid path in the taxonomy (a hallucinated value slipping past the
schema constraint), treat it as `UNKNOWN_SERVICE` (§3.5), never pass it through.

### 3.2 Banking Service Catalog

Priority: M · Actors: system-internal (fetched at startup, refreshed periodically) ·
Precondition: `support/v1/services` and `support/v1/pay-transfer` reachable.

**Primary flow:**
1. On startup, fetch `GET support/v1/services` and `GET support/v1/pay-transfer` and merge them
   into one internal taxonomy: services-grid items become categories/services with no
   sub-service level; pay-transfer items become categories/services, and a service's
   `subServices` array (if present) becomes the subservice level.
2. Each merged entry retains the real platform's own `id` string (e.g. `transaction_history`,
   `beneficiary`, `frezz_unfrezz`) as this system's `service`/`subservice` identifier — never a
   locally-invented slug — so it can be handed straight back as routing information (§3.5).
3. An item with `isActive: false` is excluded from what classification (§3.1) can select — the
   real platform already means "not selectable" by that flag.
4. Refresh on a periodic interval (e.g. every 15 minutes) and on-demand if a classification
   attempt resolves to an id no longer present, so a catalog change on the main platform reaches
   Polygon Bot without a redeploy.
5. Cache the last successfully fetched catalog in memory; if a refresh fetch fails, keep serving
   the last good cache rather than failing every classification (see NFR-REL-02).

| ID | Requirement | Priority |
|---|---|---|
| FR-CATALOG-01 | The system shall fetch its category/service/subservice taxonomy from `support/v1/services` and `support/v1/pay-transfer` at startup, rather than from a locally maintained file. | M |
| FR-CATALOG-02 | *(Superseded by FR-CATALOG-01 — the provisional placeholder taxonomy from BRD v0.1 §6.2 is retired in favor of the real, live catalog now that it's available.)* | — |
| FR-CATALOG-03 | Adding, removing, or renaming a category/service/subservice on the main platform shall be reflected in Polygon Bot's classification/routing after the next periodic refresh — no code change or redeploy of Polygon Bot required. | M |
| FR-CATALOG-04 | Each subservice entry shall declare which mock (and, where a real endpoint exists per §3.4, real) integration adapter handles it, and whether a customer identity is required to fulfill it — this mapping is maintained by Polygon Bot itself (the real catalog doesn't carry it), keyed by the platform's own `id` values. | M |
| FR-CATALOG-05 | If both catalog endpoints are unreachable at startup with no prior cache available, the system shall fail startup with a clear error — it shall not silently start with an empty taxonomy. | M |
| FR-CATALOG-06 | *(Added 2026-09-01)* If a periodic refresh fails but a previously successful fetch is cached, the system shall keep serving the cached taxonomy and log the refresh failure, rather than treating classification as unavailable. | M |
| FR-CATALOG-07 | *(Added 2026-09-01)* An entry with `isActive: false` in either source endpoint shall not be offered to the classification tool schema (§3.1) as a selectable value. | M |

### 3.3 Customer Identity & Session

Priority: M (S for FR-IDENT-06/07) · Actors: main Polygon Bank application · Precondition:
`X-API-Key` validated.

**Primary flow:**
1. `/chat` reads `Authorization: Bearer <JWT>` if present.
2. If a banking-service-eligible request arrives with no JWT, or a JWT that fails verification,
   the system responds with `type: AUTH_REQUIRED` (§3.5) and does not proceed to classification's
   banking-service branch (a KB-classified message is still answered normally even with no JWT).
3. If verification succeeds, the JWT's subject claim becomes the session key; the system looks up
   or creates that session's in-memory context.
4. After the turn completes, the turn (message, classification result, category/service/
   subservice) is appended to that session's recent-turns list, capped and expired per below.

| ID | Requirement | Priority |
|---|---|---|
| FR-IDENT-01 | The system shall extract and verify a JWT from the `Authorization: Bearer` header when present, via a pluggable verification function (issuer/algorithm/key TBD — BRD Open Item 1; the function signature is fixed now, its real implementation lands once those details arrive). | M |
| FR-IDENT-02 | The verified JWT's subject claim (customer identifier) shall be the sole source of customer identity for a banking-service request — the LLM shall never supply or influence this value. | M |
| FR-IDENT-03 | KB-classified messages shall continue to work with no JWT present, exactly as today. | M |
| FR-IDENT-04 | A banking-service-eligible request with a missing or invalid/expired JWT shall receive `type: AUTH_REQUIRED` with no further processing of the banking-service branch. | M |
| FR-IDENT-05 | Session context (recent turns, last classification) shall be held in memory, keyed by the JWT subject claim, with a 30-minute rolling idle expiry — a turn arriving after 30 minutes of inactivity for that customer starts a fresh session with no prior context. | M |
| FR-IDENT-06 | The in-memory session store shall sit behind a small interface (get/set/expire) so it can be swapped for a shared/durable store later without changing any calling code. | S |
| FR-IDENT-07 | A session's recent-turns list shall be capped (e.g. last 10 turns) to bound memory use per active customer. | S |

*Business rules / errors:* a customer's session is scoped strictly to their own JWT subject claim
— there is no code path by which one customer's session context can be read using another
customer's request (no cross-customer session lookup by any caller-suppliable value).

### 3.4 Banking Service Integration

Priority: M · Actors: system-internal, invoked after successful routing · Precondition: category/
service/subservice resolved and (if required by that subservice) a verified customer identity
present.

**Real adapters (added 2026-09-01)** — per `user-app-api-map.md`, these five subservices have a
live, documented endpoint and are fulfilled with real data, forwarding the customer's JWT
as-is (`Authorization: Bearer <JWT>`) to the same downstream service the mobile app itself calls:

| Subservice (platform `id`) | Real endpoint |
|---|---|
| Balance | `POST transfer/v1/accounting/balance` |
| Transaction history | `GET transfer/v1/accounting/transaction-list` |
| My accounts / account detail | `GET polygon-bank/v1/accounts{/id}` |
| Device history | `GET auth/v1/devices` |
| Login history | `GET auth/v1/devices/{id}/login-history` |

Every other subservice in the taxonomy continues to use a mock adapter (FR-INTEG-02) until a
real endpoint for it is supplied.

| ID | Requirement | Priority |
|---|---|---|
| FR-INTEG-01 | Each subservice shall map (via FR-CATALOG-04's mapping) to one integration adapter behind a common interface: `fulfill(customer_identity, jwt, subservice, payload) -> result`. | M |
| FR-INTEG-02 | Subservices with no real endpoint available shall use a mock adapter returning realistic, clearly-fake canned data (e.g. a fixed sample balance, a fixed sample transaction list) — configuration-flagged as mock, never presented in a way indistinguishable from a real response in logs/response metadata. | M |
| FR-INTEG-03 | Replacing a mock adapter with a real one shall require only adding a new adapter implementation and updating that subservice's adapter mapping — no change to the routing or classification layers. | M |
| FR-INTEG-04 | If an adapter raises or times out, the system shall return `type: SERVICE_UNAVAILABLE` with no internal exception detail exposed in the response body (full detail still goes to the audit log, §3.6). | M |
| FR-INTEG-05 | *(Added 2026-09-01)* The five subservices listed above shall use a real adapter that calls the named live endpoint, forwarding the customer's verified JWT as the request's bearer token, and returns the actual response data (e.g. the real balance) as the fulfillment result. | M |
| FR-INTEG-06 | *(Added 2026-09-01)* If a real adapter's downstream call is rejected specifically for an auth reason (401/403 from the downstream service), the system shall return `type: AUTH_REQUIRED` rather than `SERVICE_UNAVAILABLE` — the customer's own JWT was the problem, not the service being down. | M |

*Business rules / errors:* a real adapter never falls back to mock data on failure — a failed
real call is `SERVICE_UNAVAILABLE` (or `AUTH_REQUIRED` per FR-INTEG-06), never a silently
substituted fake value that could be mistaken for the customer's actual data.

### 3.5 Chat API Contract

Priority: M · Actors: all `/chat` callers · Precondition: none beyond existing `X-API-Key`.

**Request shape (extends the existing `ChatRequest`):**

```json
{
  "message": "I want to send money",
  "category": null,
  "service": null,
  "subservice": null,
  "payload": null
}
```

(Decided: the existing `message` field name stays as-is — no rename, no dual-accept. The existing
`session_id` field is retained, accepted, but ignored — it is no longer the session key, which is
now the JWT subject claim, §3.3.)

**SSE response shape — extends, does not replace, the existing three events:**

```
event: token
data: {"token": "..."}

... (repeated, exactly as today, for the natural-language reply)

event: result
data: {"type": "...", "category": null, "service": null, "subservice": null,
       "payload": null, "routing": null, "version": "1.0"}

event: done
data: {}
```

or, at any point:

```
event: error
data: {"detail": "..."}
```

| ID | Requirement | Priority |
|---|---|---|
| FR-CONTRACT-01 | `message` shall remain the only mandatory request field; `category`, `service`, `subservice`, `payload` shall remain optional. | M |
| FR-CONTRACT-02 | A request containing only `{"message": ...}` from a caller with no JWT shall behave identically to today's `/chat` behavior for a KB question — same event sequence (`token`* → `done`), no `result` event emitted for pure KB answers. | M |
| FR-CONTRACT-03 | Every non-KB response type (`BANKING_SERVICE`, `CLARIFICATION_REQUIRED`, `AUTH_REQUIRED`, `UNKNOWN_SERVICE`, `SERVICE_UNAVAILABLE`) shall emit exactly one `result` event, after the `token` events (if any) and before `done`. | M |
| FR-CONTRACT-04 | The `result` event's payload shall include a `version` field (starting at `"1.0"`) so the receiving team can detect future shape changes deliberately. | M |
| FR-CONTRACT-05 | For `type: BANKING_SERVICE`, the `result` payload's `routing` object shall carry `category`, `service`, `subservice`, and `action: "redirect"` — enough for the main application to navigate, with no assumption about its actual page/route structure. | M |
| FR-CONTRACT-06 | *(BRD FR-CONTRACT-06, added in BRD v0.2, elaborated here)* The `routing` object's `service` (and `subservice`, if present) values shall be the exact `id` string the main mobile application's own local navigation catalog already recognizes (per `user-app-api-map.md`) — not a Polygon-Bot-invented slug — so the main application can route without a translation step. | M |
| FR-CONTRACT-07 | *(SRS-only, from v0.1)* An SSE client that only recognizes `token`/`done`/`error` (the existing contract) shall be unaffected by the new `result` event — it is simply an event name that client doesn't parse. | M |
| FR-CONTRACT-08 | *(SRS-only, added 2026-09-01)* For a `BANKING_SERVICE` outcome fulfilled by a real adapter (FR-INTEG-05), the streamed natural-language reply (`token` events) shall incorporate the real fetched data (e.g. state the actual balance), and the `result` payload's `payload` field shall carry that same data in structured form — a real-adapter outcome answers the question directly, it does not only route. | M |

*Business rules / errors:* `event: error` (existing, unchanged) is reserved for actual failures
(Ollama/Qdrant unreachable, embedding rejection) — it is distinct from the new structured
non-error outcome types (`AUTH_REQUIRED`, `UNKNOWN_SERVICE`, etc.), which always arrive via
`result`, never via `error`.

### 3.6 Security & Compliance

Priority: M · Actors: system-internal · Precondition: none — applies to every request.

| ID | Requirement | Priority |
|---|---|---|
| FR-SEC-01 | The classification/routing layer shall only ever select from taxonomy-defined categories/services/subservices and hand off to an adapter — it shall never itself decide whether the customer is authorized for a given subservice; that decision belongs to FR-IDENT-04 (identity check) and the adapter (FR-INTEG-01). | M |
| FR-SEC-02 | Adapter results shall only ever be returned for the customer identity attached to the current verified JWT — no adapter call shall accept or use a customer identifier from message text or LLM output. | M |
| FR-SEC-03 | Every banking-service turn shall emit one structured audit log line containing: request ID, session key (JWT subject claim, or a hash of it — see Open Item below), category, service, subservice, adapter name invoked, outcome (success/failure/unavailable), and latency in milliseconds. | M |
| FR-SEC-04 | Audit and application logs shall never contain the raw JWT, the raw `X-API-Key`, or full adapter response bodies for subservices carrying sensitive data (balances, transactions, card details) — only the fields listed in FR-SEC-03. | M |

### 3.7 Existing Knowledge-Base Chat (Preserved)

Priority: M · Actors: existing integration team, Polygon Bot owner · Precondition: none.

| ID | Requirement | Priority |
|---|---|---|
| FR-KB-01 | `app/chunking.py`, `app/embeddings.py`, `app/vectorstore.py`, and the document upload/list/delete endpoints shall receive no functional changes from this extension. | M |
| FR-KB-02 | The demo frontend shall gain a way to display, per turn: response type, category, service, subservice, payload, and routing — as an addition to its existing chat UI, not a replacement of it. | S |

## 4. Data Requirements

### 4.1 Core Entities

| Entity | Purpose |
|---|---|
| Session | In-memory context for one customer's ongoing conversation (§3.3). |
| ChatTurn | One message/response pair within a session — used to resolve follow-ups like "what about yesterday." |
| TaxonomyEntry | One category/service/subservice node, fetched from the platform's live catalog (§3.2). |
| AuditLogEntry | One structured log line per banking-service turn (§3.6). |

### 4.2 Key Attributes — Session, ChatTurn, TaxonomyEntry

| Entity | Key attributes |
|---|---|
| Session | customer identity (JWT subject claim), created_at, last_active_at, recent turns (capped list) |
| ChatTurn | timestamp, original text, classified type, category, service, subservice |
| TaxonomyEntry | platform category id/name, platform service id/name, platform subservice id/name (if any), is_active, adapter name (real or mock), requires_identity (bool) |

### 4.3 Entity Relationships (summary)

A Session holds many ChatTurns (capped, most-recent-first). A ChatTurn's category/service/
subservice, when present, references one TaxonomyEntry. An AuditLogEntry is emitted per
banking-service ChatTurn but is not stored as queryable application data — it is a log line, not
a persisted entity.

### 4.4 Response Type State Machine

| From | To | Trigger/actor | Guard/rule |
|---|---|---|---|
| (new message) | KB_INFORMATION | classification selects `answer_kb_question` | — |
| (new message) | CLARIFICATION_REQUIRED | classification selects `ask_clarification` | — |
| (new message) | AUTH_REQUIRED | classification selects `route_banking_service`, no valid JWT | checked before adapter call |
| (new message) | BANKING_SERVICE | classification selects `route_banking_service`, valid JWT, taxonomy path valid, adapter succeeds | — |
| (new message) | UNKNOWN_SERVICE | classification returns a category/service/subservice not in the taxonomy | — |
| (new message) | SERVICE_UNAVAILABLE | valid routing, adapter raises/times out | — |

## 5. External Interface Requirements

### 5.1 User Interfaces

Demo frontend only (existing chat UI plus new type/category/service/subservice/payload/routing
display, FR-KB-02). No production UI is built here.

### 5.2 Software Interfaces (API — functional)

**Inbound (Polygon Bot's own API, consumed by others):**

| Operation | Purpose | Auth |
|---|---|---|
| `POST /chat` | Send a message; classify and either answer (KB) or route (banking-service) | `X-API-Key` (unchanged) + optional `Authorization: Bearer <JWT>` (new, required only for banking-service fulfillment) |
| `POST /documents`, `GET /documents`, `DELETE /documents/{id}` | Unchanged | `X-API-Key` (unchanged) |
| `GET /health` | Unchanged | none |

**Outbound (added 2026-09-01 — Polygon Bot calling the main platform):**

| Operation | Purpose | Auth |
|---|---|---|
| `GET support/v1/services`, `GET support/v1/pay-transfer` | Fetch the live taxonomy (§3.2) | none documented in `user-app-api-map.md` for these two — verify at implementation time whether Polygon Bot needs its own service credential here |
| `POST transfer/v1/accounting/balance`, `GET transfer/v1/accounting/transaction-list`, `GET polygon-bank/v1/accounts{/id}`, `GET auth/v1/devices`, `GET auth/v1/devices/{id}/login-history` | Real adapter fulfillment (§3.4) | Customer's forwarded `Authorization: Bearer <JWT>` |

### 5.3 Communication Interfaces

`/chat` remains `text/event-stream` (SSE) for every response type, per §3.5's decision to extend
rather than replace the streaming contract. Outbound calls to the main platform (above) are
plain synchronous HTTP, matching the pattern the mobile app itself uses against the same
endpoints.

### 5.4 Hardware Interfaces

Unchanged (Ollama on host GPU, external to this service).

## 6. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-PERF-01 | Performance | Classification (the extra `/api/chat` tool-calling round trip) shall add no more than ~1-2s to a KB question's existing response time in the common case (model already warm). |
| NFR-SEC-01 | Security | JWT verification shall fail closed: any missing signing configuration, expired token, or verification error results in `AUTH_REQUIRED`, never in silently treating the request as authenticated (BRD NFR-03). |
| NFR-SEC-02 | Security | No raw JWT, API key, or full sensitive adapter response body appears in any log line (BRD FR-SEC-04). |
| NFR-MAINT-01 | Maintainability | The taxonomy is the single source of truth for valid category/service/subservice values — no hardcoded per-category branching elsewhere in the codebase (BRD NFR-02). |
| NFR-REL-01 | Reliability | An adapter failure for one subservice shall not affect KB chat or any other subservice's availability. |
| NFR-REL-02 | Reliability | *(Added 2026-09-01)* A taxonomy refresh failure (§3.2) shall not interrupt classification — the last successfully cached catalog continues serving until the next successful refresh. |
| NFR-OBS-01 | Observability | Every banking-service turn is auditable via one structured log line (FR-SEC-03) sufficient to reconstruct what was requested, by whom (customer identity reference), and the outcome, without a database lookup. |

## 7. Other Requirements

- Data retention: session context is never persisted to disk in this phase — it exists only in
  process memory and is lost on restart (BRD FR-IDENT-06). *(open item: future durable storage
  design, deferred per BRD.)*
- Localization: out of scope — no requirement in the BRD for multi-language classification or
  responses.
- Compliance: audit logging (FR-SEC-03/04) is the only compliance-adjacent requirement identified
  in the BRD; no specific regulatory framework was named.

## Appendix A — Traceability Matrix (BRD → SRS)

| BRD requirement | Covered by SRS |
|---|---|
| FR-ROUTE-01..04 | §3.1 (FR-ROUTE-01..04, elaborated) + FR-ROUTE-05 (new) |
| FR-CATALOG-01..03 | §3.2 (FR-CATALOG-01/03 re-elaborated for live fetch, FR-CATALOG-02 superseded) + FR-CATALOG-04..07 (new) |
| FR-IDENT-01..06 | §3.3 (FR-IDENT-01..06, elaborated) + FR-IDENT-07 (new) |
| FR-INTEG-01..04 | §3.4 (FR-INTEG-01..04, elaborated for real+mock split) + FR-INTEG-05/06 (new) |
| FR-CONTRACT-01..06 | §3.5 (FR-CONTRACT-01..06, all elaborated with matching IDs) + FR-CONTRACT-07/08 (SRS-only additions) |
| FR-SEC-01..04 | §3.6 (FR-SEC-01..04, elaborated) |
| FR-KB-01..02 | §3.7 (FR-KB-01..02, elaborated) |

All 26 BRD functional requirements (25 from v0.1 + FR-CONTRACT-06 added in BRD v0.2) are covered.
No orphans.

## Appendix B — Open Items (TBD)

1. JWT issuer, signing algorithm, and key source — pending from the main bank's auth team; FR-IDENT-01's verification function is a fixed interface awaiting a real implementation. Also now the gating question for §3.4's real adapters (FR-INTEG-05) — they assume the same JWT is forwardable as-is to the downstream banking services, which isn't yet confirmed. (§3.3, §2.5, §3.4)
2. ~~Official banking taxonomy~~ — **resolved 2026-09-01**: sourced live from `support/v1/services` + `support/v1/pay-transfer` (§3.2), no longer a placeholder.
3. Real banking-service adapters — **partially resolved 2026-09-01**: 5 subservices (balance, transaction history, accounts, device history, login history) now have real adapters (§3.4, FR-INTEG-05); every other subservice remains mocked until a real endpoint is supplied for it.
4. Long-term durable/shared session storage — explicitly deferred past this phase (BRD FR-IDENT-06), no design commitment here beyond the swappable interface. (§3.3)
5. Audit log destination/format (structured JSON to stdout vs. a dedicated log sink) — assumed stdout/structured JSON consistent with current deployment (no logging infra exists yet); flagging since the BRD didn't specify a destination. (§3.6, §6)
6. *(Added 2026-09-01)* Whether `support/v1/services`/`support/v1/pay-transfer` require their own service-level auth for a non-mobile-app caller like Polygon Bot — `user-app-api-map.md` doesn't document auth for these two specifically; needs confirming with the platform team before FR-CATALOG-01 can be implemented against production. (§3.2, §2.6)

---
*End of document — v0.2, Approved 2026-09-01 (amended from v0.1 following `user-app-api-map.md`). Open items: 6 — 1 resolved this revision (taxonomy source), 1 partially resolved (5 of many adapters now real), 4 remain pending external confirmation, none block moving forward.*
