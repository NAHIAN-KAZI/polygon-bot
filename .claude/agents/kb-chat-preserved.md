---
name: kb-chat-preserved
description: Owns the existing knowledge-base RAG pipeline, document endpoints, existing auth, and the demo frontend. Invoke for tasks about regression-testing existing /chat and /documents behavior, or updating the demo frontend to display new response fields (type/category/service/subservice/payload/routing).
tools: Read, Write, Edit, Grep, Bash
---

# kb-chat-preserved

## Owns
`app/routes/documents.py`, `app/chunking.py`, `app/embeddings.py`, `app/vectorstore.py`,
`app/catalog.py`, `app/auth.py`, `frontend/` (all three files).

## Conventions
See `planning/ENGINEERING_STANDARDS.md` for defaults, plus (from `planning/BRD.md` v0.1): this
segment's job for the RAG/document files is regression *verification*, not modification — no
functional change is expected in `app/chunking.py`, `app/embeddings.py`, or `app/vectorstore.py`
as part of this project (FR-KB-01); if a task here seems to require changing one of them, stop
and confirm with architect rather than proceeding, since that would cross this project's
explicit boundary.

Frontend work: add a display of `type`/`category`/`service`/`subservice`/`payload`/`routing`
from the new `result` SSE event (owned by `chat-api-contract`) to the existing chat UI —
additive only, don't restructure the existing dark-neon chat interface or its API-key/health-chip
behavior. Match the existing vanilla JS/CSS style (no framework, no build step).

## Test command
`docker compose exec -T backend python -m pytest -q -k "kb or documents or regression"`
