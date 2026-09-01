# ADR-0004: Intent classification via Ollama tool-calling, not a separate pre-classifier

## Status
Accepted

## Context
FR-ROUTE-01 requires classifying every `/chat` message as a knowledge-base question, a
banking-service request, or ambiguous, before deciding which path to take. Two real approaches
were on the table: a single LLM call using `qwen3:8b`'s tool/function-calling support via
Ollama's `/api/chat`, or a separate, cheaper pre-classification step (e.g. embedding similarity
against taxonomy labels) that runs before ever invoking the LLM for a full turn.

## Decision
Use a single Ollama `/api/chat` tool-calling request, offering three tools
(`answer_kb_question`, `route_banking_service(category, service, subservice)`,
`ask_clarification(question)`) constrained to current taxonomy values (FR-ROUTE-05). Decided
directly with the project owner during the SRS drafting session (2026-08-31).

## Consequences
One model, one mechanism, one place to improve classification quality over time. The model can
naturally produce a clarifying question in the same call when genuinely ambiguous. Introduces a
dependency on `qwen3:8b` reliably supporting tool calling via `/api/chat` — this is currently an
unverified assumption (SRS §2.6) and should be spiked early in implementation (Features F-01
risk note); if it proves unreliable, this ADR should be revisited before F-06 is built on top of
it.

## Alternatives considered
**Separate lightweight pre-classifier** (e.g. embedding similarity against taxonomy label text) —
faster and cheaper for obvious cases, but adds a second mechanism to build, tune, and keep in
sync with the taxonomy independently of the LLM; rejected in favor of the single-mechanism
approach for this phase.

## Related
FR-ROUTE-01..05, NFR-PERF-01, F-01
