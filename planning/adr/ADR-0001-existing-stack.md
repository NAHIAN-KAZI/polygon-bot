# ADR-0001: FastAPI + Ollama + Qdrant stack

## Status
Accepted (retroactive)

## Context
Reverse-engineered from the existing codebase (confirmed by `agentic-harness:codebase-analyst`
survey, 2026-08-31): `requirements.txt` (`fastapi`, `uvicorn`, `qdrant-client`, `httpx`),
`app/llm.py` (calls Ollama's `/api/generate` and `/api/embeddings`), `app/vectorstore.py`
(Qdrant client), `docker-compose.yml` (Qdrant as a compose service, Ollama external via
`host.docker.internal`). This extension builds on top of this stack rather than choosing it.

## Decision
FastAPI (Python, ASGI) as the web framework, Ollama as the local LLM/embedding server
(`qwen3:8b` generation, `all-minilm` embeddings), Qdrant as the vector store. No change proposed
by this extension.

## Consequences
Makes it straightforward to add a second Ollama call (tool-calling classification, ADR-0004)
using the same `httpx`-based client pattern already in `app/llm.py`. Constrains this extension to
whatever Ollama's API supports (e.g. tool-calling must exist on the `/api/chat` endpoint —
verified as an assumption in SRS §2.6, not yet spiked).

## Alternatives considered
None — this predates the current planning effort; documented here so `/agentic-harness:architect`
and future maintainers have the decision on record rather than having to re-derive it from code.

## Related
FR-KB-01, F-08
