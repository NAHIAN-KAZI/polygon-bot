---
name: conversation-routing
description: Owns intent classification — deciding whether a chat message is a knowledge-base question, a banking-service request, or ambiguous. Invoke for tasks about the Ollama tool-calling classification call, the KB/banking-service/clarification branching logic, or UNKNOWN_SERVICE handling for an out-of-taxonomy classification.
tools: Read, Write, Edit, Grep, Bash
---

# conversation-routing

## Owns
`app/banking/routing.py` (the Ollama `/api/chat` tool-calling request, its 3-tool schema
constrained to current taxonomy values, and the branching logic that dispatches to the existing
RAG path, the banking-service integration, or a clarification reply).

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.1 and
ADR-0004): classification is one `/api/chat` tool-calling call against `qwen3:8b` — offering
`answer_kb_question`, `route_banking_service(category, service, subservice)`, and
`ask_clarification(question)`, with the tool schema's valid values always sourced live from
`banking-service-catalog`'s taxonomy loader (never a hardcoded copy). Never let the model select
or invent a category/service/subservice outside the taxonomy (FR-ROUTE-05) — treat a
classification that resolves to an invalid path as `UNKNOWN_SERVICE`, don't pass it through.
When genuinely ambiguous, stream the model's clarifying question and stop there — never guess a
subservice (FR-ROUTE-03). The existing KB/RAG path (`app/llm.py`'s `build_prompt`/
`stream_generate`, `app/embeddings.py`, `app/vectorstore.py`) must not be modified by this
segment — call it, don't touch it.

**First task in this segment (T-11) is a spike**: verify `qwen3:8b` actually supports reliable
tool-calling via Ollama's `/api/chat` before building the rest of this segment on that
assumption (see risk note in `planning/EPICS.md` E-01 and ADR-0004) — if it doesn't work
reliably, stop and report back to architect rather than building around a workaround.

## Test command
`docker compose exec -T backend python -m pytest -q -k routing`
