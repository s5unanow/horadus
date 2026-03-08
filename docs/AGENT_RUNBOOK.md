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

5. `uv run --no-sync horadus tasks local-gate --full`
When: canonical post-task local gate before push/PR; runs the full CI-parity
local validation sequence without replacing the fast iteration gate.

Compatibility wrapper:
- `make local-gate`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks local-gate --full` flow.

6. `make agent-smoke-run`
When: one-shot API serve + smoke + exit without orphan processes.

7. `make doctor`
When: diagnose local config/DB/Redis readiness quickly.

8. `uv run --no-sync horadus triage collect --lookback-days 14 --format json`
When: collect current sprint/backlog/completed/assessment inputs for backlog triage.

9. `uv run horadus pipeline dry-run --fixture-path ai/eval/fixtures/pipeline_dry_run_items.jsonl`
When: deterministic no-network/no-LLM regression exercise.

10. `make release-gate RELEASE_GATE_DATABASE_URL=<db-url>`
When: full pre-release checks before promotion.

11. `uv run --no-sync horadus tasks finish [TASK-XXX]`
When: canonical task-completion command; finishes the current task PR lifecycle
(branch/task verification -> pushed branch/PR checks -> current-head review gate
-> merge -> local `main` sync).

Compatibility wrapper:
- `make task-finish`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks finish` flow.

12. `make test-integration-docker`
When: run integration tests locally in an ephemeral Docker stack (safe defaults).
Note: the repo `pre-push` hook runs the same gate by default; bypass only with
`HORADUS_SKIP_INTEGRATION_TESTS=1` for exceptional cases.
