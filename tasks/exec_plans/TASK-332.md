# TASK-332: Fix `horadus tasks finish` when thumbs-up review-gate passes do not merge

## Status

- Owner: Codex
- Started: 2026-03-15
- Current state: In progress (implementation complete; awaiting CLI review and finish workflow)
- Planning Gates: Required - shared workflow/merge-policy behavior change with cross-caller impact

## Goal (1-3 lines)

Make `horadus tasks finish` reliably continue from review-gate success into the
merge/sync path when the configured thumbs-up signal is present and no real
merge blocker remains. Add targeted finish-path logging so future stalls are
observable without manual GitHub API inspection.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-332`)
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/orchestrator.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_gate.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/merge.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_shared.py`
  - `scripts/check_pr_review_gate.py`
  - `docs/AGENT_RUNBOOK.md`
  - `tests/horadus_cli/v2/task_finish/`
  - `tests/workflow/`
- Preconditions/dependencies:
  - Reproduce from the observed `TASK-331` lifecycle: PR green, bot `+1`, state remained `ci-green`, manual merge required
  - Audit all finish-path callers that consume review-gate results or merge-path status before changing shared behavior:
    - `scripts/check_pr_review_gate.py` -> `pr_review_gate.main`
    - `task_workflow_finish/_review_gate.py` -> spawns/parses review-gate subprocess
    - `task_workflow_finish/_review_window.py` -> consumes parsed review-gate results and thread state
    - `task_workflow_finish/orchestrator.py` -> sequences checks, review gate, merge, and final lifecycle verification
    - `task_workflow_finish/merge.py` -> owns the merge/sync/local-main completion path

## Outputs

- Expected behavior/artifacts:
  - `horadus tasks finish` merges or emits an explicit blocker after review-gate success; it does not silently stop at `ci-green`
  - Re-run from a previously green/open PR resumes the canonical merge/sync path
  - Concise phase logs for checks, review, merge, sync, and lifecycle verification
  - Opt-in debug detail for subprocess start/finish and parsed review/merge outcomes
- Validation evidence:
  - Regression tests for thumbs-up-only path and resume-from-`ci-green`
  - Repro-driven validation against a synthetic or fixture-backed green PR state

## Non-Goals

- Explicitly excluded work:
  - Broad redesign of repo workflow commands beyond `finish`
  - New persistent telemetry backend or always-on verbose logging for all commands
  - Changing the review timeout policy or reviewer identity semantics

## Scope

- In scope:
  - Review-gate-to-merge handoff in `finish`
  - Merge step resumption from `ci-green`
  - Clear blocker output when merge cannot proceed
  - Opt-in debug logging and concise normal-path phase logging
  - Regression coverage for unaffected finish paths where the same shared helpers are used
  - Update runbook/help text if the final debug surface is user-invokable
- Out of scope:
  - Non-`finish` command logging cleanup
  - GitHub review policy changes unrelated to this bug

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Preserve current workflow semantics and timeout policy; only fix the missing handoff/resume behavior and add bounded observability around it
- Rejected simpler alternative:
  - Relying on raw `gh pr merge` fallback after every stuck `finish` run; that hides workflow regressions and weakens the canonical contract
- First integration proof:
  - Reproduce the `TASK-331` style state with a green PR + reviewer `+1` and confirm `finish` reaches merge/sync without manual intervention
- Waivers:
  - None

## Plan (Keep Updated)

1. Preflight (start `TASK-332` branch, gather reproduction context, enumerate shared finish/review callers)
2. Trace the control flow from checks pass -> review-gate result -> merge attempt -> lifecycle verification; identify where `ci-green` exits without merge
3. Implement the smallest safe fix for thumbs-up pass and green-state resume behavior
4. Add concise phase logs and opt-in debug output for subprocess/result transitions in finish
5. Add regression tests for thumbs-up-only, resume-from-`ci-green`, and one unaffected current-head blocker path
6. Validate with targeted finish/workflow tests plus canonical local gate as appropriate
7. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-15: Include observability in the same task instead of a later follow-up because this bug was materially harder to diagnose due to silent waits/exits.
- 2026-03-15: Keep normal output concise; add a bounded debug surface rather than making `finish` noisy by default.

## Risks / Foot-guns

- Shared finish-path changes can regress unrelated review/blocker handling -> add at least one unaffected-caller regression test
- Extra logging can become noisy or brittle in tests -> separate concise default logs from opt-in debug detail
- Fixing the observed path too narrowly may miss resume behavior after partial prior runs -> test fresh run and resumed `ci-green` run explicitly
- Merge-state polling and subprocess timing can race on GitHub state -> log phase boundaries and verify post-merge lifecycle explicitly

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/ -q`
- `uv run --no-sync pytest tests/workflow/test_workflow_support.py -q`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-332`)
- Repro anchor:
  - `TASK-331`
  - PR `#270`
  - observed state: `ci-green` with green checks and reviewer `+1`, manual merge required
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_shared.py`
  - `scripts/check_pr_review_gate.py`
  - `docs/AGENT_RUNBOOK.md`
