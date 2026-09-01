# ADR-0010: Common adapter interface with mock implementations

## Status
Accepted

## Context
FR-INTEG-01/03 require calling a real banking-service API per subservice eventually, but no real
API specs or credentials exist yet (BRD Open Item 3, explicit out-of-scope constraint against
hardcoding fake production credentials or URLs).

## Decision
One common interface, `fulfill(customer_identity, subservice, payload) -> result`, implemented
for now by mock adapters returning realistic, clearly-fake canned data per subservice
(FR-INTEG-02), wired per-subservice via the taxonomy config (ADR-0009, FR-CATALOG-04).

## Consequences
The main Polygon Bank team can test the full round-trip flow today against mock data. Swapping a
mock for a real adapter later means writing one new implementation and updating one taxonomy
entry — no change to classification (F-01), identity (F-03), or the chat contract (F-06).

## Alternatives considered
**Hardcode mock responses inline in the routing/chat-contract code** — faster to write initially,
but directly violates FR-INTEG-03's requirement that swapping to a real API not require touching
routing/contract code; rejected.

## Related
FR-INTEG-01..04, NFR-REL-01, F-05
