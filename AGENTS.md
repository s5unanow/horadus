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
- `ai/` — LLM assets (prompts, evaluation data, benchmark results)
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

## Human-Gated Tasks

- Task entries may include the label `[REQUIRES_HUMAN]`.
- Any task marked `[REQUIRES_HUMAN]` is blocked for autonomous execution.
- Agents must not implement, close, or mark those tasks DONE until a human explicitly confirms manual completion.
- Agents may prepare scaffolding/checklists for `[REQUIRES_HUMAN]` tasks, but must stop before the manual step and report that human action is required.

## Task Dependency and Execution Rules (Hard Rule)

- When a task is not fully atomic, it must include explicit dependency metadata in `tasks/BACKLOG.md` using:
  - `**Depends On**: None` (if independent), or
  - `**Depends On**: TASK-XXX[, TASK-YYY...]` (if blocked by upstream work).
- Execution order for autonomous work is:
  1. Highest priority first (`P0` > `P1` > `P2`)
  2. Within same priority, only choose unblocked tasks (all dependencies completed)
  3. If still tied, use lowest task ID first
- Agents must not start a task whose declared dependencies are not completed.

## Project-Specific Patterns

### pgvector similarity (clustering)
```python
from datetime import datetime, timedelta

from sqlalchemy import select

from src.core.config import settings
from src.storage.models import Event

# Our config uses cosine *similarity* thresholds.
# pgvector queries often use cosine *distance* (≈ 1 - similarity when normalized).
max_distance = 1.0 - settings.CLUSTER_SIMILARITY_THRESHOLD
window_start = datetime.utcnow() - timedelta(hours=settings.CLUSTER_TIME_WINDOW_HOURS)

query = (
    select(Event)
    .where(Event.last_mention_at >= window_start)
    .where(Event.embedding.cosine_distance(target_embedding) <= max_distance)
)
```

### Log-odds conversion (always use helpers)
```python
from src.core.trend_engine import logodds_to_prob, prob_to_logodds

baseline_lo = prob_to_logodds(0.08)
new_probability = logodds_to_prob(baseline_lo + delta_log_odds)
```

### Evidence delta calculation (severity + confidence)
```python
from src.core.trend_engine import calculate_evidence_delta

delta_log_odds, factors = calculate_evidence_delta(
    signal_type="military_movement",
    indicator_weight=0.04,
    source_credibility=0.9,
    corroboration_count=3,
    novelty_score=1.0,
    direction="escalatory",
    severity=0.8,
    confidence=0.95,
)
```

### LLM calls (budget + retry + failover)
- Check budget **before** calling (`TASK-036`).
- Retry only on transient failures (429/5xx/timeouts), then fail over (`TASK-038`).
- Validate strict JSON; don’t silently coerce malformed outputs.

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
