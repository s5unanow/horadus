# Agent Instructions (Canonical)

This repo is a hobby “geopolitical intelligence” backend (not enterprise scale; expect **≤ 20 trends**). Despite being personal, it aims to be **mature and production-shaped**, adhering to **enterprise best practices where reasonable** (tests, migrations, type safety, observability, safe defaults, cost controls) without premature over-engineering.

## What This Project Is

- Headless backend that ingests public news/posts, clusters them into **events**, and updates **trend probabilities** using **log-odds**.
- Key principle: **LLM extracts structured signals; deterministic code computes probability deltas**.

## Where To Look First (Fast Orientation)

1. `tasks/CURRENT_SPRINT.md` — active execution queue (authoritative for in-progress work)
2. `PROJECT_STATUS.md` — phase-level summary and milestone narrative
3. `tasks/BACKLOG.md` — canonical task specifications and acceptance criteria
4. `docs/ARCHITECTURE.md` — system design and runtime flow
5. `docs/DATA_MODEL.md` — schema and entity definitions

## Canonical Source-of-Truth Hierarchy

When guidance conflicts, resolve it in this order.

Execution precedence:
1. Runtime truth: `src/`, `alembic/`, and `tests/`
2. Active execution plan: `tasks/CURRENT_SPRINT.md`
3. Task scope records: `tasks/BACKLOG.md` and `tasks/COMPLETED.md`
4. Phase/status summary: `PROJECT_STATUS.md`
5. Design/ops docs: `docs/`
6. Historical snapshots: `docs/POTENTIAL_ISSUES.md` and `tasks/sprints/` (non-authoritative)

Status precedence:
1. `tasks/CURRENT_SPRINT.md` for what is active now
2. `tasks/COMPLETED.md` for what is done
3. `PROJECT_STATUS.md` for high-level progress narrative

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

## Task Branching and PR Rules (Hard Rule)

- Every engineering task must run on its own dedicated git branch created from `main`.
- Branch scope must be single-task only (no mixed `TASK-XXX` implementation in one branch).
- Before creating a task branch, run sequencing preflight: `make task-preflight`.
- Start task branches via guarded command: `make task-start TASK=XXX NAME=short-name`.
- Task start is blocked unless `main` is clean/synced and there is no open non-merged task PR for the current operator.
- Open one PR per task branch and merge only after required checks are green.
- Every task PR body must include exactly one canonical metadata line: `Primary-Task: TASK-XXX` matching the branch task ID.
- After merge, delete the task branch to avoid stale branch drift.
- Task start sequence is mandatory: `git switch main` → `git pull --ff-only` → create/switch task branch.
- Task completion sequence is mandatory: merge PR → delete branch → `git switch main` → `git pull --ff-only` and verify the merge commit exists locally.
- If unrelated work is discovered mid-task, create a new task immediately but do not switch branches by default; continue current task unless the new work is a blocker/urgent.
- Never mix two tasks in one commit/PR; blockers must be handled via a separate task branch after a safe checkpoint.

## Implementation Pointers (Keep It Lean)

- Clustering threshold semantics: check `src/processing/event_clusterer.py` and `docs/ARCHITECTURE.md`.
- Probability math and log-odds helpers: `src/core/trend_engine.py`.
- LLM budget/retry/failover policy: `src/processing/` and ADRs in `docs/adr/`.
- Treat this file as a router; keep detailed implementation recipes in module docs/runbooks.

## Development Commands

- Tests: `pytest tests/ -v`
- Dev API: `uvicorn src.api.main:app --reload`
- Format/lint: `ruff format src/ tests/` and `ruff check src/ tests/`
- Typecheck: `mypy src/`

## Git Conventions

Branch naming:
- Task branches are enforced as `codex/task-XXX-short-name` via `make task-start`.
- `main` is protected and must stay merge-only.

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
