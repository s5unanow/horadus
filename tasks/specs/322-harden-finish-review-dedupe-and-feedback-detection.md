# TASK-322: Harden `horadus tasks finish` Review Request Dedupe and Feedback Detection

## Problem Statement

Recent `horadus tasks finish` PR timelines show two review-request policy
violations and one feedback-detection gap. On `#249`, the same pushed head
received two visible `@codex review` requests because Horadus only deduped
against its own hidden-marker comments, not an existing plain request. On
`#251`, a review request appeared immediately after PR creation even though
the refresh path is intended to request a new review only after a later head
change or qualifying same-head retry condition. Separately, finish can miss
new feedback because the review gate does not look at issue-comment review
results and the thread loader currently fails open when early `gh` metadata
queries fail.

The operator contract for finish is stricter than "eventually ask for review":
it should preserve current-head semantics, avoid duplicate same-head requests,
avoid auto-requesting the initial PR head, and fail closed when review state
cannot be trusted. The implementation needs to match that contract.

## Inputs

- `AGENTS.md` shared workflow/policy guardrails
- `tasks/BACKLOG.md` (`TASK-322`)
- `tasks/CURRENT_SPRINT.md`
- Observed PR histories: `#249`, `#251`
- Shared workflow surfaces:
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_refresh.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_threads.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`
- Tests:
  - `tests/horadus_cli/v2/task_finish/`
  - `tests/unit/scripts/test_check_pr_review_gate.py`

## Outputs

- Finish refresh logic that only auto-requests review for qualifying
  post-initial-head refresh conditions
- Same-head request dedupe across plain `@codex review` comments and Horadus
  marker-tagged comments
- Review-gate/reporting coverage for issue-comment review results
- Fail-closed thread metadata handling for unreadable PR/repo metadata
- Regression tests for the corrected semantics

## Non-Goals

- Changing the broader `TASK-307` / `TASK-309` current-head merge policy
- Redesigning GitHub's native auto-review triggers outside Horadus-owned logic
- Refactoring unrelated finish modules beyond what this hardening requires

**Planning Gates**: Required — shared workflow review/comment policy behavior is changing and needs explicit current-head/current-window semantics plus regression coverage.

## Phase -1 / Pre-Implementation Gates (Only If `Planning Gates: Required`)

- `Simplicity Gate`: Extend the existing finish refresh and review-gate helpers instead of adding another workflow layer; the smallest safe change is to tighten the current helper contracts.
- `Anti-Abstraction Gate`: No new top-level manager is justified; the work belongs in the existing refresh, gate, and thread helpers because the bug is semantic, not structural.
- `Integration-First Gate`:
  - Validation target: `tests/horadus_cli/v2/task_finish/` and `tests/unit/scripts/test_check_pr_review_gate.py`
  - Exercises: initial-head refresh suppression, same-head duplicate suppression, issue-comment review detection, fail-closed metadata paths
- `Determinism Gate`: Triggered — review-request conditions must be deterministic from PR history and current-head state.
- `LLM Budget/Safety Gate`: Not applicable — no model/runtime budget behavior changes.
- `Observability Gate`: Triggered — finish output should expose the relevant comment-based review state instead of silently ignoring it.

## Shared Workflow/Policy Change Checklist (Only If Applicable)

- Callers depending on this shared behavior:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/review.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/orchestrator.py`
  - `scripts/check_pr_review_gate.py`
  - `tests/horadus_cli/v2/task_finish/`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
- Add at least one regression test that proves unaffected current-head finish flow still passes when no refresh is needed.
- Define current-head/current-window semantics explicitly:
  - Plain `@codex review` request comments and Horadus marker-tagged request comments both count as existing same-head requests.
  - Issue-comment "no issues" responses from Codex count as visible review feedback for finish reporting but must still respect current-head/current-window constraints.
  - Unreadable PR/repo metadata for thread lookups is a blocker, not an implicit "no threads" result.

## Acceptance Criteria

- [ ] `horadus tasks finish` does not auto-request `@codex review` on the PR's initial head when there is no prior older-head review state or same-head timeout retry condition
- [ ] Same-head fresh-review dedupe treats an existing plain `@codex review` request and an existing marker-tagged Horadus request as equivalent blockers for another auto-request
- [ ] Current-head review reporting surfaces relevant Codex issue-comment results in addition to review objects/reactions so new comment-based feedback is not silently ignored
- [ ] Review-thread state loading fails closed when required PR/repo metadata cannot be read instead of silently treating the PR as thread-free
- [ ] Regression tests cover the intended pass path and stale/non-applicable paths for each updated signal

## Validation

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-322 --name harden-finish-review-refresh`
- `uv run --no-sync python -m pytest -q tests/horadus_cli/v2/task_finish/test_review_refresh.py tests/horadus_cli/v2/task_finish/test_review_threads.py tests/horadus_cli/v2/task_finish/test_finish_data.py tests/unit/scripts/test_check_pr_review_gate.py`
- `uv run --no-sync horadus tasks local-gate --full`
