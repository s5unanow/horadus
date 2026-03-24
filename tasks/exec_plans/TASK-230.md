# TASK-230: Add Coverage Observability Beyond Source Freshness

## Status

- Owner: Codex
- Started: 2026-03-24
- Current state: Done
- Planning Gates: Required — multi-surface runtime change touching allowlisted oversized files (`src/storage/models.py`, `src/workers/tasks.py`)

## Goal (1-3 lines)

Add a bounded coverage-health surface that distinguishes missing signal from missing or deferred processing. Persist recent coverage snapshots, export reviewable artifacts, and expose the latest health view via a read-only API distinct from source freshness.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-230`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/core/observability.py`, `src/api/routes/reports.py`, `src/workers/_task_collectors.py`, `src/workers/tasks.py`, `src/workers/celery_app.py`, `src/storage/models.py`, `alembic/versions/`
- Preconditions/dependencies: reuse source config metadata (`categories`, `themes`, collector type, tier), keep new logic out of capped hotspot files where possible

## Outputs

- Expected behavior/artifacts:
  - coverage report service over recent raw-item intake windows
  - persisted coverage snapshot rows plus exported JSON artifacts
  - scheduled worker task that computes snapshots and emits bounded metrics/log warnings
  - read-only reports endpoint for recent coverage health
- Validation evidence:
  - targeted unit tests for report aggregation, worker snapshot generation, API shaping, and observability recorders
  - repo gates for Python changes

## Non-Goals

- Explicitly excluded work:
  - changing processing policy or source freshness semantics
  - adding unbounded per-source metrics labels
  - building a new frontend/dashboard page

## Scope

- In scope:
  - language, source-family, source-tier, and configured-topic coverage segmentation
  - volume states for seen, processable, processed, deferred, and skipped-by-language
  - persisted recent snapshot payloads and artifact export path for ops/release review
  - bounded gauges/counters and warning generation for sudden drops
- Out of scope:
  - analyst-authored coverage thresholds per source
  - Telegram launch-scope changes
  - arbitrary historical coverage backfill beyond new snapshots

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - add a compact JSON snapshot table plus a service module that computes bounded dimension summaries from `raw_items` joined to `sources`
  - schedule a dedicated coverage monitor task parallel to freshness/drift sentinels
  - expose the latest snapshot from `/api/v1/reports/...` and fall back to a live build when no snapshot exists yet
- Rejected simpler alternative:
  - Prometheus-only coverage would not satisfy persisted artifact/API review requirements and would make release-gate inputs too ephemeral
- First integration proof:
  - worker run returns snapshot + artifact paths and API can serialize the same report contract
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context) ✅
2. Implement coverage service + persistence/artifacts/metrics wiring ✅
3. Validate targeted tests and repo gates ✅
4. Ship (PR, checks, merge, main sync) In progress

## Decisions (Timestamped)

- 2026-03-24: Use source config `categories`/`themes` as the bounded topic dimension instead of inventing free-form content topic inference. (Keeps coverage explainable and bounded.)
- 2026-03-24: Persist one JSON snapshot payload per monitoring run instead of normalizing every segment into its own table. (Small-scale repo, simpler queries, easier artifact parity.)
- 2026-03-24: Split the coverage API into its own router module instead of extending `src/api/routes/reports.py` past the repo line budget. (Preserves the `/api/v1/reports/coverage` surface while keeping code shape green.)

## Risks / Foot-guns

- Oversized hotspot files can regress code-shape budgets -> keep new logic in extracted modules and limit registry changes in capped files.
- Coverage semantics can blur deferred vs skipped language handling -> classify those states explicitly from `processing_status` and `error_message`.
- Metrics labels can explode if topic keys are uncontrolled -> only use normalized configured source categories/themes plus bounded fallback buckets.

## Validation Commands

- `pytest tests/unit/core/test_source_coverage.py tests/unit/core/test_observability.py tests/unit/api/test_reports.py tests/unit/workers/test_task_collectors_source_coverage.py tests/unit/workers/test_celery_setup.py tests/unit/workers/test_tasks_additional.py`
- `make agent-check`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog-only task
- Relevant modules: `src/core/source_freshness.py`, `src/core/dashboard_export.py`, `src/workers/_task_collectors.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
