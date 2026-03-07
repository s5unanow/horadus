# TASK-253: Raise Measured Runtime Coverage to 100% with Behavior-Focused Tests

## Status

- Owner: Codex
- Started: 2026-03-07
- Current state: In progress

## Goal (1-3 lines)

Raise measured runtime coverage for `src/` to 100% without padding the suite
with low-signal tests. Cover real runtime branches first, especially critical
orchestration, CLI, observability, and worker paths.

## Scope

- In scope:
  - Coverage gap analysis and prioritization
  - New or expanded unit/integration tests for uncovered runtime branches
  - Safe integration-test setup improvements needed for meaningful local/CI coverage
  - Horadus CLI entrypoint/task-flow coverage where currently weak
  - Minimal workflow/docs adjustments directly required by the coverage work
- Out of scope:
  - Enforcing the 100% threshold in hooks/CI (`TASK-257`)
  - Unrelated workflow/documentation hardening not required for coverage
  - Superficial tests that only chase lines without validating behavior

## Plan (Keep Updated)

1. Preflight (branch, tests, context, sprint/backlog updates)
2. Measure and prioritize the largest/highest-risk coverage gaps
3. Implement coverage improvements in focused slices, validating after each slice
4. Ship the task branch with evidence, then move to the next queued task

## Decisions (Timestamped)

- 2026-03-07: Start with `TASK-253` because the user made full coverage the immediate focus and `TASK-257` depends on it.
- 2026-03-07: Treat Horadus CLI surfaces as first-class coverage targets, not incidental coverage through legacy wrappers.
- 2026-03-07: Prioritize meaningful branch coverage over synthetic line-chasing; if a path is hard to cover, improve the seam or fixture rather than adding a brittle assertion.
- 2026-03-07: Complete the first coverage slice on CLI workflow surfaces before moving to broader runtime modules; this lifted `src/horadus_cli/task_commands.py` coverage from 40% to 95% and improved repo-wide unit coverage from 73% to 74%.
- 2026-03-07: Fold the next slice into API runtime seams rather than only leaf routes; `src/api/main.py`, `src/api/deps.py`, and `src/api/routes/health.py` are now covered at 100% with behavior-level tests for lifespan, exception handling, readiness, and worker-heartbeat states. Repo-wide unit coverage moved from 74% to 75% after this slice.
- 2026-03-07: Cover `src/core/tracing.py` with mock-driven tests around tracer-provider bootstrap, shared instrumentation, Celery hook registration, and disabled/unavailable guard paths; remove one impossible postrun branch while preserving behavior. Repo-wide unit coverage moved from 75% to 76% after this slice.
- 2026-03-07: Close out the thin wrapper long tail by covering `src/core/logging_setup.py` and the `src/cli.py` script entrypoint. Repo-wide unit coverage remains 76% after rounding, but these two files are now at 100% and no longer contribute avoidable misses.
- 2026-03-07: Sweep the remaining helper/runtime seams before moving into the heavier orchestration/reporting modules; `src/api/middleware/auth.py`, `src/api/middleware/agent_runtime.py`, `src/core/migration_parity.py`, `src/core/source_credibility.py`, `src/core/trend_config_loader.py`, and `src/storage/database.py` are now covered at 100%. Repo-wide unit coverage remains 76% after rounding, with misses now concentrated in larger route, reporting, ingestion, and worker modules.
- 2026-03-07: Extend low-coverage processing guardrails before tackling the biggest orchestration modules; `src/processing/degraded_llm_tracker.py` is up to 92% and `src/processing/tier2_canary.py` is up to 94% with deterministic tests around Redis persistence, degraded-mode transitions, canary selection, threshold evaluation, and canary run outcomes. Repo-wide unit coverage moved from 76% to 78%.
- 2026-03-07: Clear the next thin-tail batch before taking on the largest modules; `src/core/source_freshness.py`, `src/core/dashboard_export.py`, `src/core/drift_alert_notifier.py`, `src/core/observability.py`, `src/api/routes/auth.py`, `src/api/routes/events.py`, `src/api/routes/reports.py`, `src/api/routes/sources.py`, `src/core/cluster_drift.py`, `src/core/narrative_grounding.py`, `src/core/release_gate_runtime.py`, and `src/processing/llm_input_safety.py` are now at 100%. Repo-wide unit coverage moved from 78% to 79%.
- 2026-03-07: Push the deterministic helper and CLI/task tail further before entering the largest service modules; `src/eval/artifact_provenance.py`, `src/eval/audit.py`, `src/processing/vector_similarity.py`, and `src/processing/llm_policy.py` are now at 100%, while `src/horadus_cli/task_commands.py` improved to 98% and `src/horadus_cli/task_repo.py` improved to 96%. Repo-wide unit coverage moved from 79% to 80%.

## Risks / Foot-guns

- 100% measured coverage across `src/` is materially above the current baseline -> work in prioritized slices and keep validating deltas
- Local integration coverage currently depends on safe test DB setup -> use the repo’s safe integration path rather than unsafe truncate overrides
- Coverage pressure can incentivize brittle tests -> prefer explicit behavior assertions and reusable fixtures

## Validation Commands

- `uv run --no-sync pytest tests/unit/ -v --cov=src --cov-report=term-missing:skip-covered`
- `uv run --no-sync pytest tests/unit/test_cli.py tests/unit/scripts/ -v`
- `uv run --no-sync pytest tests/unit/core/ tests/unit/processing/ tests/unit/workers/ -v`
- `make test-integration-docker`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-253`)
- Relevant modules: `src/cli.py`, `src/horadus_cli/`, `src/workers/tasks.py`, `src/core/tracing.py`, `src/processing/`, `src/api/`
