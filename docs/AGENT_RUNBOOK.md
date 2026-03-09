# Agent Runbook

**Last Verified**: 2026-03-09

Short command index for day-to-day agent/operator work.

For RFC/design work, use the review checklist in `docs/rfc/README.md` before
circulating a proposal for implementation planning.

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
Use `tasks/specs/TEMPLATE.md` when a task needs a new or refreshed spec; keep
the contract explicit around problem statement, inputs, outputs, non-goals, and
acceptance criteria.

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
Task PRs must be titled `TASK-XXX: short summary` and include exactly one
`Primary-Task: TASK-XXX` line in the body.
If the next required action is a Docker-gated push and Docker is not ready, the
command attempts supported local auto-start before returning a blocker.
The finish flow always waits a positive review-gate timeout. Actionable
current-head review feedback blocks completion. The default review-gate
timeout is 600 seconds (10 minutes), and agents must not override or suggest
changing it unless a human explicitly asked for a different timeout. A
`THUMBS_UP` reaction from the configured reviewer on the PR summary counts as
a positive review-gate signal, but the gate still waits the full timeout
window. A silent timeout after the full wait window is allowed to continue
inside the CLI flow. Do not bypass the CLI with raw `gh pr merge`.

Treat repo-facing work as incomplete until requested deliverables, required
repo updates, and required verification/gate runs are finished or explicitly
reported blocked.
Implementation, required tests/gates, and required task/doc/status updates
remain part of the same task unless they are explicitly blocked.
If a task is blocked, report the exact missing item, the blocker causing it,
and the furthest completed lifecycle step rather than a vague
partial-completion claim.
Do not claim a task is complete, done, or finished until
`uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` passes or
`horadus tasks finish TASK-XXX` completes successfully.
The default review-gate timeout for `horadus tasks finish` is 600 seconds
(10 minutes). Agents must not override it unless a human explicitly requested
a different timeout.
Do not proactively suggest changing the `horadus tasks finish` review
timeout; wait the canonical 10-minute window unless the human explicitly
asked otherwise.
A `THUMBS_UP` reaction from the configured reviewer on the PR summary counts
as a positive review-gate signal, but the gate still waits the full timeout
window and still blocks actionable current-head review comments.

Compatibility wrapper:
- `make task-finish`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks finish` flow.

Do not skip prerequisite workflow steps such as preflight, guarded task start,
or context collection just because the likely end state looks obvious.
Prefer Horadus workflow commands over raw `git` / `gh` when the CLI covers the
step because the CLI encodes sequencing, policy, and verification
dependencies rather than just style.
Keep using the workflow until prerequisite checks, required verification
reruns, and completion verification succeed; do not stop at the first
plausible success signal.
Treat an empty, partial, or suspiciously narrow workflow result as a
retrieval problem first when the missing data likely exists.
Before concluding that no result exists, try one or two sensible recovery
steps such as broader Horadus queries, alternate filters, or the documented
manual recovery path.
If a forced fallback is still required after those recovery attempts, record
it with `horadus tasks record-friction`; do not log routine success cases or
expected empty results.
Treat repo-facing work as incomplete until requested deliverables, required
repo updates, and required verification/gate runs are finished or explicitly
reported blocked.
Implementation, required tests/gates, and required task/doc/status updates
remain part of the same task unless they are explicitly blocked.
If a task is blocked, report the exact missing item, the blocker causing it,
and the furthest completed lifecycle step rather than a vague
partial-completion claim.
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
recovery step is required. A review-gate timeout from `horadus tasks finish`
that completes silently inside the CLI is not a manual-recovery signal.

13. `uv run --no-sync horadus tasks record-friction TASK-XXX --command-attempted "..." --fallback-used "..." --friction-type forced_fallback --note "..." --suggested-improvement "..."`
When: record a real Horadus workflow gap or forced fallback in a structured
local friction log under `artifacts/agent/horadus-cli-feedback/`.
Use this only for genuine friction or forced fallback after sensible recovery
attempts, not routine success cases or expected empty results, and do not
treat the log as required reading during normal task flow.

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

## Eval Benchmark Configs

- `uv run --no-sync horadus eval benchmark` runs only the default baseline
  configs: `baseline` and `alternative`.
- GPT-5 benchmark candidates stay available for targeted comparisons, but must
  be requested explicitly with repeated `--config` flags.

## Research-Heavy Workflows

- Use bounded research mode only for triage, assessments, architecture review
  intake, and similar synthesis-heavy workflows, not for ordinary
  implementation tasks.
- Bounded research mode is: plan the sub-questions, retrieve only the repo
  evidence needed to answer them, then synthesize with explicit contradiction
  handling and clear labeling of directly supported fact versus inference.
- Cite the exact file path, task id, proposal id, or command output that backs
  each research claim; do not invent sources or smooth over conflicting
  evidence.

## Shared Workflow/Policy Guardrails

- Apply these guardrails only when changing shared workflow helpers, shared
  workflow config, or review/merge policy behavior; do not inflate unrelated
  tasks with generic process boilerplate.
- Before changing shared workflow helpers or shared workflow config,
  enumerate every caller that depends on the shared behavior.
- When shared workflow behavior changes, add at least one regression test for
  an unaffected caller so the change does not silently break other workflow
  entry points.
- Before changing review, comment, or reaction handling in merge policy
  logic, define the current-head and current-window semantics for each signal
  and regression-test both the intended pass path and at least one stale or
  non-applicable signal path.
