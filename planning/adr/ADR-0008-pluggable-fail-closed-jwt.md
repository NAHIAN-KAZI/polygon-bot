# ADR-0008: Pluggable, fail-closed JWT verification

## Status
Accepted

## Context
FR-IDENT-01 requires verifying a customer identity JWT, but the real issuer, signing algorithm,
and key source aren't available yet (BRD Open Item 1) — implementation cannot wait for them
without blocking the entire banking-service feature set. Separately, NFR-SEC-01 requires the
system to fail closed on any auth uncertainty (motivated directly by the existing codebase's
`API_KEY`-unset-means-disabled footgun found during the codebase-analyst survey — this decision
exists specifically to not repeat that pattern for JWT).

## Decision
JWT verification sits behind a fixed function interface (`verify(token) -> customer_identity |
None`) from day one. Until real signing details arrive, the implementation behind that interface
treats every token as unverifiable, meaning every banking-service request returns `AUTH_REQUIRED`
until a real verifier is wired in — never a pass-through that treats an unverifiable token as
valid.

## Consequences
Feature work (F-01, F-04, F-05, F-06) can proceed now against the fixed interface; swapping in
the real verifier later is a contained, low-risk change. Banking-service requests are
un-demoable against a real JWT until the bank's auth team provides signing details — acceptable,
since mock/manual testing can still exercise the flow with a stub verifier.

## Alternatives considered
**Decode without verifying signature** (accept any well-formed JWT as valid for now) — would
allow earlier end-to-end demoing, but violates NFR-SEC-01's fail-closed requirement and risks
being accidentally left in place; rejected outright, no exceptions.

## Related
FR-IDENT-01..04, NFR-SEC-01, F-03
