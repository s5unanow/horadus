# TASK-258: Add a Canonical Horadus Task Completion Command

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: In progress

## Goal (1-3 lines)

Make `horadus tasks finish` the single canonical task-completion engine for the
repo lifecycle. The command must verify branch/task identity, block on missing
push/PR/check/review/merge/main-sync steps, and only report success after the
repo-defined full delivery lifecycle is actually complete.

## Scope

- In scope:
  - Add a `horadus tasks finish` CLI command that drives the current task PR lifecycle
  - Reuse existing repo-owned PR-scope and review-gate checks instead of duplicating policy logic
  - Convert `make task-finish` into a thin compatibility wrapper to the CLI
  - Convert `scripts/finish_task_pr.sh` into a thin compatibility wrapper to the CLI
  - Update agent-facing docs to point to the CLI as the canonical completion path
  - Add unit coverage for success flow and representative blocked states
- Out of scope:
  - Broader lifecycle-state modeling (`TASK-259`)
  - Full local CI-parity gate work (`TASK-260`)
  - Workflow-doc/skill drift enforcement beyond the finish-command surface (`TASK-263` / `TASK-264`)

## Plan (Keep Updated)

1. Preflight (preserve dirty sprint/backlog intake, sync `main`, start task branch)
2. Implement CLI finish flow and demote legacy wrapper surfaces
3. Validate with focused unit tests plus repo-required local gates
4. Ship via PR/checks/merge/main sync using the new canonical command

## Decisions (Timestamped)

- 2026-03-08: Carry the existing `tasks/BACKLOG.md` and `tasks/CURRENT_SPRINT.md` intake edits into the `TASK-258` branch/PR because the user explicitly required those dirty planning updates to stay in scope of the first task.
- 2026-03-08: Keep `scripts/check_pr_task_scope.sh` and `scripts/check_pr_review_gate.py` as reusable policy helpers, but move the overall task-completion orchestration into `horadus tasks finish` so only one lifecycle engine remains.
- 2026-03-08: Make `make task-finish` call the CLI directly and keep `scripts/finish_task_pr.sh` only as a compatibility shim to avoid a parallel workflow authority.

## Risks / Foot-guns

- The finish flow mutates git/GitHub state -> add clear blocker/next-action messages and keep a dry-run-safe validation path
- `gh` behavior around merge/delete can be idempotent but inconsistent -> tolerate already-merged states while still verifying the final synced-main result
- Over-duplicating helper logic would create a second lifecycle implementation -> reuse the existing scope/review helper scripts rather than re-encoding their policy

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v1/test_cli.py tests/unit/scripts/test_finish_task_pr.py -v`
- `make agent-check`
- `make docs-freshness`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-258`)
- Relevant modules: `src/horadus_cli/task_commands.py`, `Makefile`, `scripts/finish_task_pr.sh`, `docs/AGENT_RUNBOOK.md`, `README.md`
