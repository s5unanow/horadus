# TASK-309: Refresh Finish Review State Immediately After a New PR Head Is Pushed

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: Done
- Planning Gates: Required — shared finish/review behavior, GitHub review semantics, and workflow-policy updates

## Goal (1-3 lines)

Fix `horadus tasks finish` so a new invocation after review-feedback updates
immediately refreshes review state for the current PR head. The CLI should
resolve outdated stale threads, request fresh review once for the new head, and
only then begin a fresh canonical review window for that head, replacing the
old window entirely.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-309`)
  - `artifacts/agent/temp-report-canonical-flow-issues.md`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/workflow/test_task_workflow.py`
  - `tests/workflow/test_workflow_support.py`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
  - `ops/skills/horadus-cli/SKILL.md`
  - `ops/skills/horadus-cli/references/commands.md`
  - `tasks/CURRENT_SPRINT.md`
- Preconditions/dependencies:
  - `TASK-307` is merged and remains the current finish baseline.
  - `TASK-309` must be active in `tasks/CURRENT_SPRINT.md` or otherwise
    explicitly authorized before guarded start.

## Outputs

- Expected behavior/artifacts:
  - A rerun of `horadus tasks finish TASK-XXX` after a new PR head is pushed
    immediately:
    - refreshes current-head metadata,
    - revalidates task-close and check state for that head,
    - auto-resolves outdated unresolved review threads from the older head when
      GitHub still treats them as blockers,
    - posts exactly one fresh review request for the new head when needed,
    - cancels the old review-window context,
    - then begins a fresh 600-second canonical review window for that head.
  - The same-head timeout/unresolved-thread retry behavior from `TASK-307`
    remains preserved.
  - Documentation and skill guidance stay aligned with the current finish flow.
  - The canonical review timeout is sourced from one shared owner/constant
    rather than repeated as ad hoc inline values in the rerun flow, especially
    between `task_workflow_core.py` and `pr_review_gate.py`, while still
    allowing extraction to a small neutral workflow-shared owner if needed.
- Validation evidence:
  - Regression coverage for the new-head rerun path.
  - Regression coverage that same-head timeout/thread retry still works.
  - Workflow/policy surfaces updated and checked for drift.

## Non-Goals

- Explicitly excluded work:
  - A general FSM rewrite of all `finish` behavior.
  - Manual PR recovery for `TASK-308`.
  - Broad review-gate policy changes beyond this rerun/new-head refresh gap.

## Scope

- In scope:
  - New-invocation finish behavior after a PR head changes.
  - Immediate stale-thread resolution for outdated unresolved blockers.
  - Immediate fresh-review request for the new head, deduped per head SHA.
  - Revalidation of current-head task-close state and green checks before the
    fresh review window starts.
  - Explicit reset of the prior review window when a fresh review request is
    issued for a newer head.
  - Consolidating the canonical 600-second review timeout behind one shared
    owner/constant used by the finish review loop, reusing the current shared
    workflow owner where possible.
  - Policy/runbook/skill wording for this specific finish behavior.
- Out of scope:
  - Changing the canonical 10-minute review window.
  - Changing the same-head timeout semantics except to preserve them.
  - Reworking unrelated start/close-ledger workflow behavior.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `finish` as the orchestrator, but add an explicit new-head refresh
    phase before the fresh review window begins on rerun.
- Rejected simpler alternative:
  - “Just wait again and let the next timeout handle it” is not acceptable,
    because it can wait without clearing stale blockers or asking for fresh
    review.
- First integration proof:
  - Reproduce the `TASK-308` rerun shape in tests: old-head feedback fixed by a
    new commit, stale thread becomes outdated, rerun `finish`, and verify
    immediate resolution + fresh-review request before waiting.
- Waivers:
  - None by default.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - Run `uv run --no-sync horadus tasks preflight`.
   - Run `uv run --no-sync horadus tasks safe-start TASK-309 --name finish-refresh-rerun`.
   - Run `uv run --no-sync horadus tasks context-pack TASK-309`.
   - Enumerate current callers/owners of the finish review-loop behavior,
     including:
     - `task_workflow_core.py`
     - `pr_review_gate.py`
     - `repo_workflow.py`
     - `task_workflow_policy.py`
     - `tests/horadus_cli/v2/test_cli.py`
       - direct `_maybe_request_fresh_review(...)` and rerun review-loop regressions
     - `tests/workflow/test_task_workflow.py`
     - `tests/workflow/test_workflow_support.py`
     - `tests/unit/scripts/test_check_pr_review_gate.py`
   - Confirm the preserved baselines:
     - silent-timeout-allow path,
     - same-head timeout/thread retry path,
     - already-merged convergence,
     - branch-policy `--auto` fallback.

2. Implement
   - Add an explicit rerun/new-head refresh phase before the review wait begins.
   - Reuse the existing shared workflow timeout owner wherever possible; if
     direct reuse would create a module cycle or violate workflow-module
     isolation, extract a small neutral shared-workflow constant owner rather
     than introducing another inline `600`.
   - When a new head is detected on rerun:
     - revalidate head alignment,
     - rerun task-close-state validation,
     - rerun required-check validation and require green current-head checks,
     - resolve outdated unresolved threads from the older head if GitHub still
       exposes them as blockers,
     - request fresh review once for the new head,
     - discard the old review-window context for the previous head,
     - only then begin a fresh 600-second review window for the new head.
   - Preserve the same-head unresolved-thread timeout path from `TASK-307`.
   - Use one shared canonical timeout owner/constant for the review window so:
     - `task_workflow_core.py` and `pr_review_gate.py` do not diverge,
     - docs/policy helpers can derive from the same source where appropriate,
     - tests may import/assert against the shared owner instead of duplicating
       ad hoc `600` literals where that does not overstep module isolation.
   - Keep the `pr_review_gate.py` <-> `finish` contract machine-consumable and
     stable.

3. Validate
   - Add regression coverage for:
     - rerun-after-new-head immediate stale-thread resolution,
     - rerun-after-new-head immediate fresh-review request,
     - rerun-after-new-head starts a new review window rather than continuing the
       old one,
     - no duplicate fresh-review request for the same head,
     - same-head timeout/thread retry still requesting fresh review,
     - already-merged convergence,
     - branch-policy `--auto` fallback,
     - `pr_review_gate.py` reads the review timeout default from the shared
       workflow owner instead of carrying its own inline `600`.
   - Verify the runtime timeout default is no longer duplicated inline between
     `task_workflow_core.py` and `pr_review_gate.py`, and that `pr_review_gate.py`
     now reads the timeout from a shared workflow owner.
   - Revalidate unaffected caller coverage:
     - `tests/unit/scripts/test_check_pr_review_gate.py`
   - Run docs/policy drift checks for:
     - `AGENTS.md`
     - `docs/AGENT_RUNBOOK.md`
     - Horadus CLI skill surfaces
     - `repo_workflow.py`
     - `task_workflow_policy.py`

4. Ship (PR, checks, merge, main sync)
   - Keep the task branch single-task scoped.
   - Close ledgers on the PR head before the final `horadus tasks finish TASK-309` run.
   - Merge through the canonical finish flow and sync local `main`.

## Decisions (Timestamped)

- 2026-03-12: Treat the `TASK-308` rerun gap as a distinct follow-up instead of
  folding it back into the already-merged `TASK-307`.
- 2026-03-12: Preserve `TASK-307` same-head timeout/thread retry behavior while
  adding the missing new-head rerun refresh behavior.

## Risks / Foot-guns

- Refresh logic can duplicate fresh-review requests -> dedupe per PR head SHA and regression-test reruns on the same head.
- Refresh logic can miss stale GitHub blockers -> regression-test outdated unresolved thread resolution before the new review wait begins.
- New-head refresh can regress preserved finish baselines -> explicitly rerun those baselines in validation.
- Review-window reset can accidentally keep using the prior timer context ->
  regression-test that a fresh review request for a newer head always starts a
  new canonical 600-second window.
- Timeout handling can drift if 600s is duplicated inline -> use a single shared
  owner/constant and keep docs/tests aligned to that source without creating
  new cross-layer imports that violate module isolation.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_cli.py -q -k "finish and review"`
- `uv run --no-sync pytest tests/workflow/test_task_workflow.py -q -k "finish or review_gate"`
- `uv run --no-sync pytest tests/workflow/test_workflow_support.py -q -k "review or timeout"`
- `uv run --no-sync pytest tests/unit/scripts/test_check_pr_review_gate.py -q`
- `if rg -n "default=600" tools/horadus/python/horadus_workflow/pr_review_gate.py; then exit 1; fi`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `rg -n "600 seconds \\(10 minutes\\)|10-minute review window|fresh review request|same-head timeout" AGENTS.md docs/AGENT_RUNBOOK.md ops/skills/horadus-cli/ tools/horadus/python/horadus_workflow/repo_workflow.py tools/horadus/python/horadus_workflow/task_workflow_policy.py`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `artifacts/agent/temp-report-canonical-flow-issues.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
