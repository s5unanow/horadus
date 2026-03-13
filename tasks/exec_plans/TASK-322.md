# TASK-322: Harden `horadus tasks finish` Review Request Dedupe and Feedback Detection

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: Done
- Planning Gates: Required — shared workflow review/comment policy behavior is changing and must preserve current-head semantics across finish, refresh, and gate helpers

## Goal (1-3 lines)

Fix the finish review-refresh flow so it does not auto-request review on the
initial PR head, does not duplicate same-head requests when a plain request
already exists, and does not silently miss comment/thread feedback state.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-322`)
  - `tasks/specs/322-harden-finish-review-dedupe-and-feedback-detection.md`
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_refresh.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_threads.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`
  - `tests/horadus_cli/v2/task_finish/`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
- Preconditions/dependencies:
  - Preserve the current-head review semantics from `TASK-307` / `TASK-309`
  - Keep the public `horadus tasks finish` CLI behavior and result format stable except for the corrected reporting lines
  - Treat GitHub-native PR-open review triggers as external; only Horadus-owned auto-requests should change here

## Outputs

- Expected behavior/artifacts:
  - Refresh logic that distinguishes initial-head state from true post-push refresh conditions
  - Same-head request dedupe across plain and marker-tagged request comments
  - Review-gate reporting for comment-based Codex results
  - Fail-closed thread metadata reads
- Validation evidence:
  - Focused finish/review regression tests
  - Relevant workflow gate coverage proving unaffected callers still work

## Non-Goals

- Explicitly excluded work:
  - Reworking the broader merge policy, timeout policy, or branch-alignment logic
  - Changing GitHub/Codex server-side behavior outside the repo-owned workflow helpers

## Scope

- In scope:
  - Tighten pre-review refresh detection and request dedupe
  - Improve finish review reporting for Codex issue comments
  - Fail closed on unreadable thread metadata
  - Add regression tests for the observed PR-history cases
- Out of scope:
  - New top-level workflow modules
  - Unrelated cleanup in finish helpers that does not serve these semantics

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep the fix inside the existing refresh, gate, and thread helpers so the public workflow surface stays stable.
- Rejected simpler alternative:
  - Only deduping marker-tagged comments is too narrow because actual PR history includes plain `@codex review` requests on the same head.
- First integration proof:
  - Reproduce the observed semantics with focused finish/review tests instead of relying only on live PR anecdotes.
- Waivers:
  - None currently.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - Add the task intake on `main`, run guarded preflight, and start `TASK-322`.
   - Reconfirm the exact PR-history failure cases and map them to current helpers.
2. Implement
   - Tighten refresh-state detection so the initial head does not trigger an auto-request.
   - Deduplicate same-head requests across plain and marker comments.
   - Surface comment-based Codex feedback and fail closed on unreadable thread metadata.
3. Validate
   - Run focused finish/review tests and local gate coverage.
   - Check that unaffected refresh/gate paths still behave correctly.
4. Ship (PR, checks, merge, main sync)
   - Commit task-close state on the branch, open PR, finish through the canonical workflow, and verify local `main` sync.

## Decisions (Timestamped)

- 2026-03-13: Treat initial-head auto-requesting as a bug, not an allowed convenience. (reason: the intended contract is "refresh after subsequent push or qualifying retry", and PR `#251` violated that)
- 2026-03-13: Treat plain `@codex review` comments as equivalent to marker-tagged Horadus requests for same-head dedupe. (reason: PR `#249` shows same-head duplicate requests when only one side carries the marker)
- 2026-03-13: Treat unreadable thread metadata as a blocker, not an empty-thread success path. (reason: finish should fail closed when review state is unreliable)

## Risks / Foot-guns

- Over-tightening refresh detection could suppress legitimate same-head retry requests after timeout -> preserve the explicit timeout retry path and cover it with regression tests
- Expanding comment-based reporting could accidentally treat stale/older-head comments as current-head feedback -> keep current-window/current-head filtering explicit in the review gate
- Failing closed on metadata errors can make finish noisier during transient GitHub issues -> keep blocker messages actionable and specific

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-322 --name harden-finish-review-refresh`
- `uv run --no-sync python -m pytest -q tests/horadus_cli/v2/task_finish/test_review_refresh.py tests/horadus_cli/v2/task_finish/test_review_threads.py tests/horadus_cli/v2/task_finish/test_finish_data.py tests/unit/scripts/test_check_pr_review_gate.py`
- `uv run --no-sync horadus tasks local-gate --full`
- `uv run --no-sync horadus tasks finish TASK-322`

## Notes / Links

- Spec:
  - `tasks/specs/322-harden-finish-review-dedupe-and-feedback-detection.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_refresh.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_threads.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
- Related tasks:
  - `tasks/exec_plans/TASK-307.md`
  - `tasks/exec_plans/TASK-309.md`
