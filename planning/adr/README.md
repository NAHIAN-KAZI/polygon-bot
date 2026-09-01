# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [0001](ADR-0001-existing-stack.md) | FastAPI + Ollama + Qdrant stack | Accepted (retroactive) |
| [0002](ADR-0002-static-api-key-auth.md) | Static shared API key as the outer auth gate | Accepted (retroactive) |
| [0003](ADR-0003-sse-transport.md) | SSE as the /chat streaming transport | Accepted (retroactive) |
| [0004](ADR-0004-intent-classification-via-tool-calling.md) | Intent classification via Ollama tool-calling | Accepted |
| [0005](ADR-0005-session-keyed-by-jwt-identity.md) | Session keyed by JWT customer identity | Accepted |
| [0006](ADR-0006-in-memory-session-store.md) | In-memory session store behind a swappable interface | Accepted |
| [0007](ADR-0007-result-sse-event.md) | Extend SSE with a `result` event | Accepted |
| [0008](ADR-0008-pluggable-fail-closed-jwt.md) | Pluggable, fail-closed JWT verification | Accepted |
| [0009](ADR-0009-taxonomy-as-yaml-config.md) | Banking service taxonomy as a YAML config file | Accepted |
| [0010](ADR-0010-mock-adapter-interface.md) | Common adapter interface with mock implementations | Accepted |
