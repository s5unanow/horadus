# TASK-192: Cluster drift sentinel (scheduled quality monitor)

## Status

- Owner: Codex
- Started: 2026-03-02
- Current state: Done

## Goal (1-3 lines)

Add a scheduled, warn-only cluster drift sentinel that computes deterministic
proxy quality signals and persists daily artifacts for operator review.

## Scope

- In scope:
  - Drift summary computation module
  - Scheduled Celery task + beat wiring
  - Warn-only threshold configuration
  - Daily JSON artifact persistence
  - Unit tests for determinism and output shape
- Out of scope:
  - Hard blocking release policy
  - UI/dashboard for drift artifacts

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-02: Persisted sentinel output as JSON artifacts under `artifacts/cluster_drift/` to avoid immediate schema/migration overhead.
- 2026-03-02: Kept sentinel warn-only with configurable thresholds to prevent noisy hard-block regressions.

## Risks / Foot-guns

- Artifact directory must remain writable by worker runtime.
- Language drift baseline depends on prior artifact availability.

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_cluster_drift.py tests/unit/workers/test_celery_setup.py -v -m unit`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-192`)
- Relevant modules: `src/core/cluster_drift.py`, `src/workers/tasks.py`, `src/workers/celery_app.py`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`
