# Agent Instructions (Codex / Claude / Gemini)

This repo is a hobby “geopolitical intelligence” backend (not enterprise scale; expect **≤ 20 trends**). Despite being personal, it aims to be **mature and production-shaped**, adhering to **enterprise best practices where reasonable** (tests, migrations, type safety, observability, safe defaults, cost controls) without premature over-engineering.

## What This Project Is

- Headless backend that ingests public news/posts, clusters them into **events**, and updates **trend probabilities** using **log-odds**.
- Key principle: **LLM extracts structured signals; deterministic code computes probability deltas**.

## Where To Look First (Fast Orientation)

1. `PROJECT_STATUS.md` — current phase and what’s actually implemented vs planned
2. `tasks/CURRENT_SPRINT.md` — what to do next (source of truth for active work)
3. `docs/ARCHITECTURE.md` — system design and data flows
4. `docs/DATA_MODEL.md` — schema and entity definitions

## Repo Map

- `src/api/` — FastAPI app and routes
- `src/core/` — domain logic (trend math, config)
- `src/storage/` — DB engine + SQLAlchemy models
- `src/ingestion/` — collectors (may be stubbed early)
- `src/processing/` — LLM + clustering + pipeline (may be stubbed early)
- `src/workers/` — async/background workers (may be stubbed early)
- `config/` — YAML configuration (`trends/`, `sources/`)
- `docs/` — architecture, glossary, ADRs (`docs/adr/`)
- `tasks/` — backlog, sprint, and detailed specs (`tasks/specs/`)
- `tests/` — unit/integration tests

## Working Agreements (Personal-Scale)

- Prefer **simple, debuggable** solutions over distributed complexity.
- Optimize for: **bounded cost**, **traceability**, and **iterability**.
- Keep **production-like discipline**: clear module boundaries, migrations, idempotency, retries/backoff, structured logs, and tests for core logic.
- Avoid adding infrastructure unless it enables a concrete next milestone.

## Guardrails

- Don’t introduce network calls in tests.
- Keep probability updates explainable (store factors used for deltas).
- Any LLM usage must be protected by budget/limits where possible.

## Common Commands

- Tests: `pytest tests/ -v`
- Dev API: `uvicorn src.api.main:app --reload`
- Format/lint: `ruff format src/ tests/` and `ruff check src/ tests/`
- Typecheck: `mypy src/`

## Git Conventions

See `CLAUDE.md` for branch/commit conventions used in this repo.
