# Business Requirements Document (BRD)

## Polygon Bot — Banking Intent & Service Routing

| | |
|---|---|
| **Document title** | Polygon Bot — Banking Intent & Service Routing — Business Requirements |
| **Version** | 0.2 |
| **Date** | 2026-09-01 |
| **Author** | Nahian Kazi |
| **Status** | Approved |

---

## 1. Purpose

Polygon Bot is a working knowledge-base chat service for Polygon Bank: customers (and an
external integration team, via a shared API key) ask questions, the system retrieves relevant
document content and answers with an LLM. This document defines the requirements for extending
Polygon Bot so it can also recognize when a customer is asking to *do* something banking-related
(check a balance, send money, pay a bill, block a card, etc.) and hand back structured
information the main Polygon Bank application can use to take the customer to the right place —
without Polygon Bot performing the banking action itself, and without breaking any of its
existing knowledge-base behavior.

## 2. Background

Today, every message sent to Polygon Bot is treated as a knowledge-base question: it is answered
using retrieved document content and the LLM, with no concept of customer identity, session
continuity, or "the customer wants to do something." Authentication is a single shared secret
for the whole integration, not tied to any individual customer.

The main Polygon Bank application — its frontend, backend, real banking APIs, transaction
processing, and customer login/identity — is owned and operated entirely outside this project.
That team wants Polygon Bot to additionally recognize banking-service requests ("what's my
balance," "I want to send money") and tell them *which* banking feature the customer means, so
their own application can navigate the customer there. Polygon Bot does not perform the banking
action, does not own the customer's identity, and does not build the destination page — it
identifies intent and hands off structured routing information.

## 3. Business Objectives

1. Enable Polygon Bot to recognize a banking-service request and identify its category, service,
   and subservice, returning structured information the main Polygon Bank application can use to
   redirect the customer to the correct feature. (Priority: Must-have)
2. Preserve all existing knowledge-base chat behavior and its current API contract exactly as-is
   for the existing integration team — this extension must be purely additive. (Must-have)
3. Establish a foundation — customer identity handling, a reconfigurable service taxonomy, and a
   replaceable banking-service integration layer — that can absorb the bank's official service
   taxonomy and real banking APIs later without redesigning the system. (Must-have)
4. Make the new routing/classification behavior easy to verify during development via the
   existing demo/test frontend. (Should-have)

## 4. Scope

### 4.1 In scope

- Distinguishing, per incoming message, whether the customer is asking a knowledge-base question
  or requesting a banking service/action, and asking a clarifying question when that's genuinely
  ambiguous rather than guessing.
- A reconfigurable catalog of banking categories, services, and subservices, seeded with a
  reasonable placeholder set, replaceable later with the bank's official set without redesigning
  how routing works.
- Accepting an authenticated customer identity (via a token issued by the main Polygon Bank
  application) so banking-service requests are tied to a real, verified customer — never to an
  identity the chatbot or the LLM invents.
- Retaining enough conversation context within a session that a natural follow-up ("what about
  yesterday") is understood in relation to the prior banking request.
- Returning structured routing information (category/service/subservice, and enough context for
  the main application to navigate the customer) for banking-service requests, including a
  version marker on that structure so the receiving team can handle future changes deliberately.
- A replaceable integration point for calling real banking-service APIs later; until those are
  available, returning realistic mock data so the receiving team can test full round-trip
  behavior today.
- Clear, structured handling for: ambiguous requests, unrecognized services, unavailable banking
  integrations, and missing/invalid customer authentication on a banking-service request.
- Extending the chat request with optional fields (category, service, subservice, payload) that
  a caller may already know, without making any of them mandatory.
- Updating the existing demo/test frontend only as needed to display and verify the new
  classification/routing behavior.

### 4.2 Out of scope

- Executing actual banking transactions or operations (transfers, payments, card actions, etc.)
  — Polygon Bot identifies and routes, it does not perform.
- Building the destination banking pages/screens the customer is routed to.
- Owning or operating customer login, identity issuance, or the main application's authentication
  infrastructure — Polygon Bot only consumes an identity token issued elsewhere.
- Providing production banking API integrations, URLs, or credentials for anything beyond the
  read-only queries the main platform has already exposed and documented (see Assumptions) —
  everything else is supplied by the main Polygon Bank backend team when available.
- The bank's official category/service/subservice taxonomy — sourced live from the main
  platform's own catalog rather than invented or hand-maintained here (see Assumptions).

## 5. Stakeholders & User Roles

| Role | Description |
|---|---|
| Bank Customer | End user, interacting via the main Polygon Bank application (not directly with Polygon Bot); their identity flows in via a token from that application. |
| Main Polygon Bank Application Team | Owns the frontend, backend, real banking APIs, and customer identity/login; consumes Polygon Bot's chat API and acts on its routing responses. |
| External Integration Team | Existing consumer of today's knowledge-base-only chat API (per current integration documentation); must be unaffected by this extension. |
| Polygon Bot Owner | Owns and operates this chatbot service (this project). |

## 6. Functional Requirements

Requirements are grouped by module. Priority uses **M** (Must-have), **S** (Should-have),
**C** (Could-have).

### 6.1 Conversation Routing
*Recognizing what kind of request a message represents, and asking for clarification when it's genuinely unclear.*

| ID | Requirement | Priority |
|---|---|---|
| FR-ROUTE-01 | The system must classify each incoming message as a knowledge-base question, a banking-service request, or ambiguous/needing clarification. | M |
| FR-ROUTE-02 | Knowledge-base questions must continue to be answered exactly as they are today (retrieval + LLM answer), unaffected by the new classification step. | M |
| FR-ROUTE-03 | When a request is ambiguous (e.g. "I need help with my card"), the system must ask a clarifying question rather than guessing a category, service, or subservice. | M |
| FR-ROUTE-04 | A caller may optionally supply an already-known category, service, and/or subservice with the request, which the system uses instead of re-classifying from scratch. | M |

### 6.2 Banking Service Catalog
*The reconfigurable list of banking categories, services, and subservices the system can recognize and route to.*

| ID | Requirement | Priority |
|---|---|---|
| FR-CATALOG-01 | The system must maintain a catalog of banking categories, each with one or more services, each with one or more subservices. | M |
| FR-CATALOG-02 | The initial catalog is a provisional, reasonable placeholder (see Assumptions) — a starting point for development and testing, not the bank's official structure. | M |
| FR-CATALOG-03 | Categories, services, and subservices must be addable, removable, or renameable without redesigning how classification or routing works. | M |

### 6.3 Customer Identity & Session
*Establishing who the customer is for a banking-service request, and retaining enough conversation context across turns.*

| ID | Requirement | Priority |
|---|---|---|
| FR-IDENT-01 | The system must accept an authentication token issued by the main Polygon Bank application, identifying the requesting customer. | M |
| FR-IDENT-02 | Banking-service requests must be tied to the customer identity established by that token — never to an identity supplied by the message text or generated by the LLM. | M |
| FR-IDENT-03 | Knowledge-base questions must continue to work without requiring any customer identity token, exactly as today. | M |
| FR-IDENT-04 | A banking-service request made without a valid customer identity token must receive a clear, structured "authentication required" response distinct from a generic error, so the main application can prompt the customer to log in. | M |
| FR-IDENT-05 | Within a session, the system must retain enough context that a natural follow-up message is understood in relation to the customer's prior banking-service request (e.g. "what about yesterday" following a balance request). | M |
| FR-IDENT-06 | For this phase, session context may be held only for the life of the running service (lost on restart); the design must not preclude replacing this with a durable, shared store later without a redesign. | S |

### 6.4 Banking Service Integration
*Calling out to get the actual data or confirmation a banking-service request needs, once identified.*

| ID | Requirement | Priority |
|---|---|---|
| FR-INTEG-01 | Once a banking-service request is fully identified (category, service, subservice, and any required details), the system must be able to call an external service to fulfill it. | M |
| FR-INTEG-02 | Where a real external banking service is not yet available, the system must return realistic mock data instead, clearly distinguishable as mock in configuration (never presented as real in a way that could reach a production customer unnoticed). | M |
| FR-INTEG-03 | The integration point for each service must be replaceable with a real banking API later without changing how requests are classified or routed. | M |
| FR-INTEG-04 | If an external service is unavailable or fails, the system must return a clear, structured "service unavailable" response without exposing internal error detail. | M |

### 6.5 Chat API Contract
*How the chat request/response is extended, and what stays guaranteed for existing callers.*

| ID | Requirement | Priority |
|---|---|---|
| FR-CONTRACT-01 | The chat request's text field remains the only mandatory field; category, service, subservice, and a free-form payload are optional additions. | M |
| FR-CONTRACT-02 | A request containing only the text field must behave identically to today's behavior, for both knowledge-base and any pre-existing caller. | M |
| FR-CONTRACT-03 | A banking-service response must include enough structured information (category, service, subservice, and routing/next-step information) for the main application to navigate the customer, without Polygon Bot assuming or hard-coding knowledge of the main application's actual page structure. | M |
| FR-CONTRACT-04 | The structured response format must carry a version marker so the receiving team can detect and deliberately handle future changes to its shape. | M |
| FR-CONTRACT-05 | Responses must be clearly typed (e.g. knowledge-base answer, banking-service routing, clarification needed, authentication required, unrecognized service, service unavailable) so the receiving application can branch its handling reliably. | M |
| FR-CONTRACT-06 | *(Added 2026-09-01)* The routing information returned for a banking-service response must use the identifier the main mobile application's own navigation already recognizes for that service, so the main application can route the customer without needing a separate translation step. | M |

### 6.6 Security & Compliance
*Keeping authorization, sensitive data handling, and auditability where they belong.*

| ID | Requirement | Priority |
|---|---|---|
| FR-SEC-01 | The system (the LLM specifically) must never be treated as the authorization decision-maker for a banking-service request — it identifies intent and selects a category/service/subservice; actual authorization, validation, and execution belong to the banking service being called. | M |
| FR-SEC-02 | The system must not expose sensitive banking data (balances, transactions, account/card details) beyond what is explicitly returned by an authorized banking-service call for the authenticated customer. | M |
| FR-SEC-03 | Every banking-service request/response must be logged with enough structured detail (request identifier, session identifier, a reference to the customer identity, category/service/subservice, which integration was called, outcome, timing) to support an audit trail. | M |
| FR-SEC-04 | Logs must never contain raw authentication tokens, passwords, PINs, or other secrets, and must avoid capturing full sensitive account/transaction detail beyond what auditing genuinely requires. | M |

### 6.7 Existing Knowledge-Base Chat (Preserved)
*What must remain true about the system's current capability.*

| ID | Requirement | Priority |
|---|---|---|
| FR-KB-01 | Document upload, retrieval, and knowledge-base chat answering must continue to function exactly as they do today, for both existing and new callers. | M |
| FR-KB-02 | The existing demo/test frontend must continue to support today's knowledge-base workflows unmodified, aside from additions needed to display the new classification/routing behavior for testing. | M |

## 7. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | Classifying and routing a banking-service request must not noticeably slow down or degrade the response time customers experience for ordinary knowledge-base questions. |
| NFR-02 | The banking-service catalog must be maintained in one central, editable place — not scattered as repeated logic throughout the system — so changing it doesn't require touching unrelated code. |
| NFR-03 | Authentication/authorization for banking-service requests must fail closed: if customer identity cannot be verified, the request must be treated as unauthenticated, never silently allowed through. |
| NFR-04 | The system must remain usable and testable by the Polygon Bot owner via the existing demo frontend throughout this extension's development. |

## 8. Assumptions & Constraints

- The main Polygon Bank application's real backend, transaction APIs, login/identity system, and
  final destination pages are owned elsewhere and are not built or modified as part of this
  project.
- The initial banking category/service/subservice catalog is a provisional placeholder, based on
  a typical retail-banking structure; the bank's official structure will be supplied later and is
  expected to replace it without requiring a redesign. **Updated 2026-09-01:** the official
  structure turns out to already exist as a live catalog the main mobile application consumes
  today (`GET support/v1/services`, `GET support/v1/pay-transfer`) — this system fetches its
  taxonomy from those same endpoints rather than maintaining a separately hand-edited copy, so
  the two never drift apart.
- The specific technical details of the main application's authentication token (issuer, signing
  method, claim contents) are not yet available; validation of that token is treated as a
  pending, pluggable piece of the design (see Open Items).
- Real external banking-service APIs are not available for most banking-service requests during
  this phase; realistic mock data is used in their place. **Updated 2026-09-01:** the main
  application's frontend/backend team has since provided the real platform's API map
  (`user-app-api-map.md`), which shows five read-only banking queries already have live,
  callable endpoints (balance, transaction history, account list/detail, device history, login
  history). Where a real endpoint exists, this system calls it directly rather than mocking it;
  mock data remains the fallback wherever no real endpoint yet exists (money transfer, bill
  payment, card actions, and everything else in the taxonomy).
- The existing chat API contract, as relied upon by the current external integration team, must
  remain fully backward compatible — this extension is additive only.
- For this phase, conversation/session context may live only in the running service's memory
  (lost on restart); a durable or shared store is explicitly deferred, not ruled out, for later.

## 9. Glossary

| Term | Meaning |
|---|---|
| Knowledge-base (KB) question | A question answered using retrieved document content and the LLM — the system's existing capability. |
| Banking-service request | A message where the customer wants to perform or check something banking-related (balance, transfer, bill payment, card action, etc.), rather than ask a general question. |
| Category / Service / Subservice | The three-level structure used to classify a banking-service request (e.g. Payments → Money Transfer → Send Money). |
| Routing information | The structured category/service/subservice (and related detail) returned to the main Polygon Bank application so it can navigate the customer. |
| Customer identity token | An authentication token issued by the main Polygon Bank application, identifying the authenticated customer to Polygon Bot. |
| Session | The continuity of a customer's conversation across multiple messages, sufficient to resolve natural follow-ups. |

---

## Open Items (TBD)

1. Exact customer identity token format — issuer, signing method, and claim contents — to be
   provided by the main Polygon Bank application's authentication team before this can be fully
   implemented. (§6.3)
2. Official banking category/service/subservice taxonomy — to be provided later, replacing the
   provisional catalog. (§6.2)
3. Real banking-service API specifications and credentials — to be provided later, replacing mock
   data. (§6.4)
4. Whether/when conversation session context needs to move from in-memory to a durable or shared
   store — explicitly deferred past this phase, but noted as expected future work. (§6.3)
5. *(Added 2026-09-01, resolved)* Official taxonomy and 5 real banking-service endpoints
   (balance, transaction history, accounts, device history, login history) turned out to already
   exist — see Assumptions. JWT signing/validation specifics (Open Item 1) remain outstanding;
   the main application team has confirmed they will supply the token, but exact
   issuer/algorithm/key details are still pending.

---
*End of document — v0.2, Approved 2026-09-01 (amended from v0.1 following `user-app-api-map.md`, provided by the main application's frontend/backend team). Open items: 3 remaining (JWT specifics, real banking API details for actions beyond the 5 read-only queries, future session storage).*
