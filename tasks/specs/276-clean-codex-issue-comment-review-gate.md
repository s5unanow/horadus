# TASK-276: Treat Clean Codex Review Issue Comments as Review-Gate Success

## Problem Statement

`horadus tasks finish` now fails closed when the required Codex review does not
arrive before timeout. In practice, Codex can respond to `@codex review` with a
clean issue comment such as “Didn't find any major issues” instead of creating
a current-head PR review. The existing review gate only inspects PR reviews and
inline review comments, so clean PRs can still block until timeout even though
Codex already reviewed the current head.

## Inputs

- Current finish flow in `src/horadus_cli/task_commands.py`
- Review-gate helper in `scripts/check_pr_review_gate.py`
- Codex GitHub behavior observed on PR `#209`
- Existing finish/review-gate tests in `tests/unit/test_cli.py` and `tests/unit/scripts/`

## Outputs

- Review-gate behavior that treats a clean Codex issue comment for the current
  PR head as a machine-checkable success condition, or another equivalent
  current-head success signal
- Regression tests that keep stale-head and wrong-author comments from
  satisfying the gate
- Updated operator guidance if the recognized success signal changes

## Non-Goals

- Removing the review gate
- Treating arbitrary issue comments as approval
- Allowing stale comments from an older head commit to satisfy the gate

## Acceptance Criteria

- [ ] Clean Codex issue comments for the current PR head satisfy the finish review gate
- [ ] Stale clean comments from an older head commit do not satisfy the gate
- [ ] Comments from non-Codex authors do not satisfy the gate
- [ ] Actionable current-head Codex review comments still fail the gate
- [ ] Tests cover clean-comment success, stale-head rejection, and actionable inline-comment failure

## Validation

- `uv run --no-sync pytest tests/unit/scripts/test_check_pr_review_gate.py tests/unit/test_cli.py -k review_gate -q`
- `uv run --no-sync horadus tasks local-gate --full`
