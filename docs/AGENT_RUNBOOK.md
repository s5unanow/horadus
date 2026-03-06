# Agent Runbook

**Last Verified**: 2026-03-06

Short command index for day-to-day agent/operator work.

## Canonical Commands

1. `uv run --no-sync horadus tasks preflight`
When: before creating a task branch from `main`.

2. `make agent-safe-start TASK=XXX NAME=short-name`
When: start implementation for one task branch with eligibility and sequencing checks.

3. `uv run --no-sync horadus tasks context-pack TASK-XXX --format json`
When: collect backlog/spec/sprint context for an implementation task.

4. `make agent-check`
When: fast local quality gate (lint + typecheck + unit tests).

5. `make agent-smoke-run`
When: one-shot API serve + smoke + exit without orphan processes.

6. `make doctor`
When: diagnose local config/DB/Redis readiness quickly.

7. `uv run --no-sync horadus triage collect --lookback-days 14 --format json`
When: collect current sprint/backlog/completed/assessment inputs for backlog triage.

8. `uv run horadus pipeline dry-run --fixture-path ai/eval/fixtures/pipeline_dry_run_items.jsonl`
When: deterministic no-network/no-LLM regression exercise.

9. `make release-gate RELEASE_GATE_DATABASE_URL=<db-url>`
When: full pre-release checks before promotion.

10. `make task-finish`
When: complete PR lifecycle (checks -> current-head review gate -> merge -> local `main` sync).

11. `make test-integration-docker`
When: run integration tests locally in an ephemeral Docker stack (safe defaults).
Note: the repo `pre-push` hook runs the same gate by default; bypass only with
`HORADUS_SKIP_INTEGRATION_TESTS=1` for exceptional cases.
