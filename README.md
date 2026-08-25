# RAG Chatbot

FastAPI backend for document-grounded chat, backed by a local Ollama (`qwen3:8b` for
generation, `all-minilm` for embeddings) and Qdrant for vector storage.

## Setup

```bash
cp .env.example .env
# edit .env and set API_KEY to a real secret
docker compose up --build
```

Requires an Ollama instance reachable at `OLLAMA_BASE_URL` (default assumes it's already
running on the host at port 11434, as `qwen3:8b` and `all-minilm` need to be pulled there).

Open `http://localhost:8000/` for the test UI, or use the API directly below.

## API

See [INTEGRATION.md](./INTEGRATION.md) — the doc to hand to any team consuming this API
(endpoints, curl examples, SSE event format, error codes). That's the contract; keep it in sync
with `app/routes/` if endpoints change.

## Architecture notes

- Text extraction: `pypdf` (page-aware) for PDF, `python-docx` for DOCX, raw decode for TXT/MD.
- Chunking: recursive splitter (paragraph → sentence → char), ~800 chars with ~120 char
  overlap (tunable via `CHUNK_SIZE` / `CHUNK_OVERLAP`). Markdown files are split on headers first.
- Retrieval: query embedded with `all-minilm`, top-k cosine search in Qdrant filtered by
  `MIN_RELEVANCE_SCORE` (default 0.3, tunable) so weakly-related chunks don't get stuffed into
  context; chunks + citations fed into the `qwen3:8b` prompt.
- Generation: `qwen3:8b`'s thinking mode is disabled by default (`OLLAMA_THINK=false`) — this
  roughly halved chat latency in testing (~11s → ~3s warm) since the model skips its internal
  reasoning trace and answers directly. Set `OLLAMA_THINK=true` if you want chain-of-thought back.
- Ingestion embeds chunks concurrently (`asyncio.gather`, capped at 4 in-flight) rather than
  one-by-one, though the actual speedup depends on Ollama's own parallel-request capacity.
- Document metadata (filename, chunk count, upload time) is kept in a small JSON catalog at
  `/app/data/documents.json` (persisted via the `app_data` volume); chunk vectors + text live in Qdrant.
- The `ollama` container already running on this host is pinned to GPU 1 — this stack's own
  services (backend, Qdrant) are CPU-only and don't need GPU config.

## Known limitations

- Single uvicorn worker (no `--workers` flag) — fine for one internal team's traffic, but chat
  requests are one-at-a-time within this process; scale with `--workers N` behind a shared-nothing
  setup if concurrent load grows (the JSON document catalog isn't safe for multiple processes as-is).
- The Ollama server observed on this host runs with `-np 1` (one parallel request slot), so even
  though this app fires embedding calls concurrently, Ollama itself may still serialize them.
- First request after any restart of either container pays a one-time model-load cost into GPU
  memory (~50s seen in testing) before responding — expected, not a bug.
- No re-ranking step; retrieval is pure top-k cosine similarity plus a score floor. Fine for a
  small/medium document set — revisit if the corpus grows large enough that top-k alone starts
  missing the right chunk.
