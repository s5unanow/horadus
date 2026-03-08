# Agent Runbook

**Last Verified**: 2026-03-06

Short command index for day-to-day agent/operator work.

## Canonical Commands

1. `uv run --no-sync horadus tasks preflight`
When: before creating a task branch from `main`.

2. `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
When: canonical autonomous task-start command; enforces sprint eligibility and
sequencing checks before creating the task branch.

Compatibility wrapper:
- `make agent-safe-start TASK=XXX NAME=short-name`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks safe-start` flow.

3. `uv run --no-sync horadus tasks context-pack TASK-XXX`
When: collect backlog/spec/sprint context for an implementation task.

4. `make agent-check`
When: fast local quality gate (lint + typecheck + unit tests).

5. `uv run --no-sync horadus tasks local-gate --full`
When: canonical post-task local gate before push/PR; runs the full CI-parity
local validation sequence without replacing the fast iteration gate.
If the gate reaches the Docker-backed integration step and the daemon is not
ready, it attempts best-effort local auto-start on supported environments
before failing with a specific blocker.
If `UV_BIN` is set to an absolute `uv` path, every `uv`-backed full-gate step
uses that same executable, including package-build validation.

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

11. `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
When: inspect machine-checkable task lifecycle state.
Use the strict form to verify repo-policy completion; success requires state
`local-main-synced`.
When running from detached `HEAD` (for example in CI or a throwaway worktree),
pass the task id explicitly; branch inference is only supported on canonical
task branches.

12. `uv run --no-sync horadus tasks finish TASK-XXX`
When: canonical task-completion command; finishes the current task PR lifecycle
(branch/task verification -> pushed branch/PR checks -> current-head review gate
-> merge -> local `main` sync -> strict lifecycle verification).
If the next required action is a Docker-gated push and Docker is not ready, the
command attempts supported local auto-start before returning a blocker.

Compatibility wrapper:
- `make task-finish`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks finish` flow.

Do not claim a task is complete, done, or finished until
`uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` passes or
`horadus tasks finish TASK-XXX` completes successfully.
Local commits, local tests, and a clean working tree are checkpoints, not
completion.
Do not stop at a local commit boundary unless the user explicitly asked for a
checkpoint.
Resolve locally solvable environment blockers before reporting blocked.

Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
needed workflow step yet, or when the CLI explicitly tells you a manual
recovery step is required.

13. `uv run --no-sync horadus tasks record-friction TASK-XXX --command-attempted "..." --fallback-used "..." --friction-type forced_fallback --note "..." --suggested-improvement "..."`
When: record a real Horadus workflow gap or forced fallback in a structured
local friction log under `artifacts/agent/horadus-cli-feedback/`.
Use this only for genuine friction or forced fallback, not routine success
cases, and do not treat the log as required reading during normal task flow.

14. `uv run --no-sync horadus tasks summarize-friction --date YYYY-MM-DD`
When: generate the compact daily friction report at
`artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md`.
The report groups duplicate patterns, highlights candidate CLI/skill
improvements, and keeps follow-up work in human-review-only form. Do not
auto-create backlog tasks from the report.

15. `make test-integration-docker`
When: run integration tests locally in an ephemeral Docker stack (safe defaults).
Note: the repo `pre-push` hook runs the same gate by default; bypass only with
`HORADUS_SKIP_INTEGRATION_TESTS=1` for exceptional cases.
If Docker auto-start is unsupported in the current environment, start Docker
manually before rerunning the workflow command.
