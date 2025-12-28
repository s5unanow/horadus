# Agent Instructions (Canonical)

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

## Workflow (How To Work In This Repo)

Before starting work:
- Read `tasks/CURRENT_SPRINT.md` and any relevant `tasks/specs/*.md`.
- Skim `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` for context.
- Run tests relevant to your change (at minimum unit tests).

After completing work:
- Update `tasks/CURRENT_SPRINT.md` (mark DONE) and move finished tasks to `tasks/COMPLETED.md`.
- Update `PROJECT_STATUS.md` when a milestone meaningfully changes.
- Add/adjust ADRs under `docs/adr/` for major decisions.
- Ensure formatting/linting/tests pass.

## Guardrails

- Don’t introduce network calls in tests.
- Keep probability updates explainable (store factors used for deltas).
- Any LLM usage must be protected by budget/limits where possible.

## Development Commands

- Tests: `pytest tests/ -v`
- Dev API: `uvicorn src.api.main:app --reload`
- Format/lint: `ruff format src/ tests/` and `ruff check src/ tests/`
- Typecheck: `mypy src/`

## Git Conventions

Branch naming:
- `main`
- `feature/TASK-XXX-short-description`
- `fix/TASK-XXX-short-description`
- `refactor/short-description`
- `docs/short-description`

Commit message format:
- `<type>(<scope>): <subject>`
- Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`
- Scope (optional): `api`, `core`, `storage`, `ingestion`, `processing`, `workers`, `repo`

Commit hygiene:
- Keep commits atomic (one logical change).
- Include `TASK-XXX` in body/footer when applicable.
- Prefer subject ≤ 50 chars; wrap body at ~72 chars.

## Environment Variables

Copy `.env.example` to `.env`. LLM provider selection is documented in `docs/adr/002-llm-provider.md`.

Typical required values:
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY` (don’t commit real keys)
