# Engineering Standards

> Enforced by `/agentic-harness:architect` on every task before it's marked ✅ DONE — see
> `architect.md`'s Architecture Review step. Generic defaults below; add
> project-specific conventions under "Project-specific additions" as they
> emerge. Don't relitigate the defaults per task — they're the baseline.

## Non-negotiable

- **Tests pass.** A task without a passing test run is not done — no
  exception, no "looks correct to me."
- **No cross-segment edits without sign-off.** A segment agent only
  touches its own `owns_paths` (see `planning/project.config.yaml`'s
  `architecture.segments`). Needing to touch another segment's files means
  the task was mis-scoped or the segmentation is stale — flag it, don't
  just do it. This includes swarms (`architecture.swarms`): a swarm
  coordinates parallel dispatch on one task, it never merges paths.
- No dead code, no commented-out blocks, no unused imports/variables left behind.

## Judgment calls (architect enforces at review time)

- No premature abstraction — three similar lines beat a speculative helper.
- No unrequested scope creep — a bug fix doesn't need a refactor riding along.
- Match existing patterns in the segment before introducing a new one.
- Comments explain WHY (a non-obvious constraint, a workaround), never WHAT
  (the code already says that).
- No new dependency, framework, or architectural pattern introduced without
  it being called out explicitly in the task or flagged to the user first.

## Project-specific additions

*(from `planning/BRD.md` v0.1)*

- **Banking taxonomy lives in one centralized, data-driven config** — never a hardcoded
  if/elif/switch chain per category/service/subservice scattered through the codebase
  (BRD NFR-02).
- **Auth for banking-service requests fails closed.** If customer identity cannot be verified,
  treat the request as unauthenticated — never silently allow it through (BRD NFR-03).
- **Never log raw authentication tokens, passwords, PINs, or secrets**, and avoid capturing full
  sensitive account/transaction detail beyond what an audit trail genuinely needs (BRD FR-SEC-04).
- **The LLM is never the authorization decision-maker** and never the source of customer
  identity for a banking-service request — both always come from the verified token/backend,
  never from LLM-generated or message-derived parameters (BRD FR-IDENT-02, FR-SEC-01).
