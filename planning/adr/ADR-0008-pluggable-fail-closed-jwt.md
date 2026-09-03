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

**Confirmed 2026-09-03 (T-20, live login against the bank's dev environment):** the real
implementation is now wired in behind this ADR's fixed interface, exactly as anticipated — this
is not a reversal of the decision. A live login (test credentials from the bank's team) against
`https://internet-banking.dev-polygontech.xyz/auth/v1/auth/login` returned a real token, decoded
(unverified) to confirm:
1. Algorithm is **HS256** (symmetric shared secret), not an asymmetric scheme — matches
   `api-endpoints-guide.md`'s independent note that Kong Gateway validates JWTs as HS256. There is
   no public key/JWKS to fetch; verification requires the bank's actual shared secret.
2. `sub` claim is the customer's phone number (already correct as the session key per ADR-0005 —
   no change needed there), `iss` is the literal string `"internet-banking"`, no `aud` claim,
   `exp - iat = 900s` (15-minute token lifetime).

`verify_jwt()` now performs real HS256 signature/issuer/expiry validation via `PyJWT`, but stays
fail-closed exactly as this ADR requires: with no `JWT_HS256_SECRET` configured (still the case —
the bank hasn't provided the actual secret value yet), it returns `None` unconditionally before
attempting to decode anything, verified live against a real, valid, unexpired bank-issued token
(still correctly rejected as `AUTH_REQUIRED`). The fail-closed guarantee this ADR establishes is
unchanged; only the "not yet available" signing details it anticipated are now mostly resolved.
