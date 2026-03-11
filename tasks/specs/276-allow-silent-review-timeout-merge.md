# TASK-276: Allow Finish Merge After Silent Review Timeout

## Problem Statement

`horadus tasks finish` now fails closed when the required Codex review does not
arrive before timeout. That is too strict for the real workflow because Codex
review delivery is not guaranteed: quota exhaustion or integration behavior can
leave a PR with no feedback at all. The repo policy should instead be: wait the
full review window, force agents to address actionable feedback if it arrives,
and allow merge when the timeout expires with no actionable current-head
feedback.

## Inputs

- Current finish flow in `src/horadus_cli/task_commands.py`
- Review-gate helper in `scripts/check_pr_review_gate.py`
- Operational behavior observed on PR `#209`
- Existing finish/review-gate tests in `tests/horadus_cli/v1/test_cli.py` and `tests/unit/scripts/`

## Outputs

- Review-gate behavior that waits the full timeout and allows merge when no
  actionable current-head Codex feedback appears during that window
- Regression tests that keep actionable feedback blocking merge while allowing
  silent timeout
- Updated operator guidance that matches the 10-minute wait-then-merge policy

## Non-Goals

- Removing the review gate
- Ignoring actionable current-head review feedback
- Requiring an explicit clean-review success signal before merge

## Acceptance Criteria

- [ ] `horadus tasks finish` waits the full configured review timeout before deciding whether merge may continue
- [ ] If actionable current-head Codex review feedback appears during the wait window, the finish flow blocks and requires the feedback to be addressed
- [ ] If no actionable current-head Codex feedback appears by timeout expiry, the finish flow may continue without requiring an explicit clean-review success signal
- [ ] Silence caused by review quota exhaustion or equivalent no-feedback conditions does not deadlock task completion
- [ ] Tests cover silent-timeout allow behavior, actionable-feedback blocking, and representative stale-head/non-current-head edge cases

## Validation

- `uv run --no-sync pytest tests/unit/scripts/test_check_pr_review_gate.py tests/horadus_cli/v1/test_cli.py -k review_gate -q`
- `uv run --no-sync horadus tasks local-gate --full`
