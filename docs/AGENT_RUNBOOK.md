# Agent Runbook

**Last Verified**: 2026-03-03

## Canonical Commands

1. `make agent-safe-start TASK=XXX NAME=short-name`
When: start any autonomous engineering task branch (includes sprint-eligibility and sequencing checks).

2. `make task-preflight`
When: dry-run sequencing checks without creating a branch.

3. `make task-finish`
When: complete PR lifecycle for the current task branch (checks -> merge -> sync main).

4. `make doctor`
When: verify local workflow prerequisites (required git hooks).

5. `make hooks`
When: install/refresh required pre-commit, pre-push, and commit-msg hooks.
