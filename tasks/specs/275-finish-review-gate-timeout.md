# TASK-275: Enforce Finish-Command Review-Gate Timeouts Without Agent Bypass

## Problem Statement

`horadus tasks finish` is the repo’s canonical completion command, but recent
task delivery still fell back to raw `gh pr merge` after checks were green.
That creates process drift exactly where the workflow is supposed to be strict.

The repo should require agents to stay on the CLI path, wait the configured
review-gate timeout, and fail closed if the required review condition is still
not satisfied. Zero-timeout or equivalent “don’t wait” bypasses should not be
accepted.

## Inputs

- Canonical workflow policy in `AGENTS.md`
- Operator guidance in `docs/AGENT_RUNBOOK.md`
- Finish-flow implementation in `src/horadus_cli/task_commands.py`
- Existing finish/review-gate unit coverage in `tests/horadus_cli/v1/test_cli.py` and `tests/unit/scripts/`

## Outputs

- Finish-path behavior that enforces a positive review-gate timeout and blocks on timeout expiry
- Agent/operator guidance that keeps `horadus tasks finish` as the only normal completion path when the CLI is available
- Regression tests for timeout enforcement and representative bypass attempts

## Non-Goals

- Changing the underlying review policy or removing the review gate
- Adding a second completion workflow outside `horadus tasks finish`
- Auto-merging on timeout

## Acceptance Criteria

- [ ] `horadus tasks finish` remains the canonical completion path when the CLI is available; agent-facing guidance no longer leaves room for raw `gh pr merge` bypass during normal task completion
- [ ] The finish flow always honors a positive review-gate timeout and fails closed when the timeout expires without satisfying the required review condition
- [ ] Passing `0` (or any equivalent no-wait value) cannot be used to skip the review-gate wait path
- [ ] Timeout failures surface a specific blocker and next required action instead of encouraging a raw merge fallback
- [ ] Tests cover the positive-timeout requirement, timeout-expiry blocker behavior, and representative bypass attempts

## Validation

- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
- Targeted `pytest` coverage for finish/review-gate behavior
