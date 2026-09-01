# Planning

Everything in this folder is one shareable bundle — drop the whole
`planning/` directory in front of a teammate and they can see exactly where
the project stands, what's decided, what's still open, and what was
assumed once confirmed. Maintained by `/agentic-harness:plan` and the stage
commands it drives (`:brd`, `:srs`, `:design`, `:features`, `:adr`,
`:epics`); status here always matches `project.config.yaml`'s
`planning.stages`. Prior versions of every artifact live in `versions/` —
nothing is ever silently overwritten (see `planning-protocol.md`'s
Versioning section).

_Last updated: 2026-08-31_

## Calibration

Knowledge level: working · Pressure level: standard *(set on the first
`/agentic-harness:plan` run)*

Entry point: existing-project — extending the working `polygon-bot` RAG
chatbot (FastAPI backend + Ollama/qwen3:8b + Qdrant) with banking intent
routing. Has UI: no — main Polygon Bank frontend is owned elsewhere; the
demo frontend here is test-only and gets incremental updates, not a
planned design deliverable.

## Delivery

Mode: whole project at once. Sequenced E-02 → E-03 → E-01 → E-04 (WSJF,
respecting dependencies — see `EPICS.md`'s Delivery plan section).

## Stage status

| Stage | Artifact | Version | Status | Approved |
|---|---|---|---|---|
| BRD | [BRD.md](BRD.md) | 0.1 | approved | 2026-08-31 |
| SRS | [SRS.md](SRS.md) | 0.1 | approved | 2026-08-31 |
| Design | [DESIGN.md](DESIGN.md) | — | skipped | — |
| Features | [FEATURES.md](FEATURES.md) | 0.1 | approved | 2026-08-31 |
| ADRs | [adr/](adr/README.md) | 10 | approved | 2026-08-31 |
| Epics | [EPICS.md](EPICS.md) | 0.1 | approved | 2026-08-31 |

Status values: `pending` (not started) · `draft` (written, not yet
reviewed) · `in-review` · `approved` · `skipped` (e.g. Design, for a
project with no UI).

## Open Items (TBD)

_(none yet — populated as stage commands surface genuinely unresolved
decisions; each artifact keeps its own numbered Open Items section, this
is the cross-artifact rollup)_

## Assumptions & Constraints

_(none yet — confirmed background conditions land here once a stage
command gets a real answer, distinct from Open Items above which are still
unresolved)_
