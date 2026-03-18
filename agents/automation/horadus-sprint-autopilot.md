# Automation: Horadus Sprint Autopilot

Use `/Users/s5una/projects/horadus` as the repository root and `AGENTS.md`
there as the canonical workflow policy.

## Safety Gates Before Any Repo Work

1. Resolve `CODEX_HOME_RESOLVED="${CODEX_HOME:-$HOME/.codex}"`.
2. Acquire exclusive ownership of the external lock at:
   - `$CODEX_HOME_RESOLVED/locks/horadus-sprint-autopilot`
3. If the lock is already held, cannot be acquired cleanly, or appears stale or
   broken, stop immediately and report a concise blocker instead of forcing
   takeover.
4. After the lock is acquired, confirm the repo is idle:
   - current branch is exactly `main`
   - working tree is clean
5. If either repo-idle check fails, stop immediately without changing anything.
6. Sync local `main` before any start preflight:
   - run `git pull --ff-only`
   - if it fails, stop and report the blocker instead of starting or resuming work

## Resume Before Selection

- Before selecting a fresh sprint task, check for an open non-merged task PR
  owned by the current operator.
- If one exists, derive its `TASK-XXX` identifier and re-run:
  - `uv run --no-sync horadus tasks finish TASK-XXX`
- After that resume-path `finish` invocation returns, stop this automation run
  even if the task PR merged successfully.
- Do not start a second task while an in-flight task PR still exists.

## Task Selection

- Only if no in-flight task PR exists, read `tasks/CURRENT_SPRINT.md`.
- Pick the next eligible sprint task from the active task list order.
- Skip any task marked `[REQUIRES_HUMAN]` or otherwise explicitly blocked.
- Process at most one task in this run.

## Canonical Workflow

After selecting a fresh candidate task:

1. Run `uv run --no-sync horadus tasks eligibility TASK-XXX --format json`.
2. If the task is not eligible, stop and report the blocker instead of
   improvising around policy.
3. Run `uv run --no-sync horadus tasks preflight`.
4. Run `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`.
5. Read the task spec or exec plan referenced by the sprint/backlog context.
6. Implement the task end to end on its dedicated task branch.
7. Run required validation:
   - relevant targeted tests
   - `make agent-check` when Python changes
   - any stronger gate required by the task scope
8. Update the task ledgers/docs required by `AGENTS.md`.
9. Run `uv run --no-sync horadus tasks finish TASK-XXX`.

## Failure Handling

- If blocked by ambiguity, permissions, CI/platform failures, human-only
  approval, or automation-lock issues, stop that task and report a concise
  blocker summary.
- Do not begin a second task in the same run.
- Release the external lock on exit.
