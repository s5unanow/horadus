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
