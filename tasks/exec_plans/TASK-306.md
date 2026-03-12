# TASK-306: Unblock Canonical Finish When Only Outdated Review Threads Remain

## Status

- Owner:
- Started:
- Current state: Not started
- Planning Gates: Not Required — targeted finish-path workflow correction on existing review-gate semantics

## Goal (1-3 lines)

Keep `horadus tasks finish TASK-XXX` fully canonical through merge when the PR
is green and the only remaining GitHub blocker is an outdated unresolved review
thread. Preserve normal blocking behavior for actionable current-head feedback.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-306`)
  - canonical finish/review policy in `AGENTS.md`
  - command/operator guidance in `docs/AGENT_RUNBOOK.md`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `scripts/check_pr_review_gate.py`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
  - GitHub review-thread and auto-merge state queried by `horadus tasks finish`
  - `tests/workflow/`
- Preconditions/dependencies:
  - preserve current-head review blocking semantics
  - preserve the positive review-timeout wait window
  - preserve merge safety when checks are red or the PR head is stale

## Outputs

- Expected behavior/artifacts:
  - `horadus tasks finish` no longer requires manual thread resolution when the
    only remaining PR thread blockers are outdated on a green current head
  - actionable current-head review comments still block finish before merge
  - stale-thread handling is explicit in CLI output and operator docs
  - no raw GraphQL/manual GitHub fallback is required for the stale-thread-only case
- Validation evidence:
  - regression coverage for outdated unresolved-thread pass path
  - regression coverage for current-head actionable review blocker path
  - end-to-end finish-path tests stay green

## Non-Goals

- Explicitly excluded work:
  - changing the 600-second default review timeout
  - weakening current-head review comment blocking rules
  - bypassing required checks or merge policy
  - redesigning all review-gate semantics beyond the stale-thread-only case

## Scope

- In scope:
  - define the exact stale-thread semantics used by canonical finish
  - keep GitHub merge-blocker behavior aligned with the repo-owned finish policy
  - update finish-path messaging/docs for the stale-thread-only case
  - add regression coverage for stale vs actionable review-thread states
- Out of scope:
  - broad PR review UX redesign
  - non-finish workflow commands
  - changes to task-start, safe-start, or planning intake behavior

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: treat outdated unresolved review threads as non-blocking for canonical finish when the current head is green and no actionable current-head review feedback remains
- Rejected simpler alternative: leave the CLI unchanged and require manual GraphQL thread resolution; this keeps a known canonical-flow gap alive
- First integration proof: current `TASK-305` reproduction where auto-merge was enabled but GitHub still blocked on an outdated unresolved thread
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory every current caller and checker involved in finish/review-thread semantics before changing shared workflow behavior, including:
     - `horadus tasks finish`
     - `scripts/check_pr_review_gate.py`
     - `tests/unit/scripts/test_check_pr_review_gate.py`
     - finish-path coverage in `tests/horadus_cli/v2/test_cli.py`
     - the post-review auto-merge wait path inside `finish_task_data`
   - define the exact distinction between:
     - current-head actionable review feedback
     - outdated unresolved review threads
     - already-resolved review threads
   - define the exact handoff between:
     - review-gate pass/timeout success
     - unresolved-thread blocker evaluation
     - auto-merge enable/wait completion
   - confirm which GitHub surfaces currently drive merge blocking versus CLI blocking

2. Implement
   - update finish-path review-thread handling so stale/outdated unresolved threads do not force a manual fallback after the review gate has cleared
   - preserve blocking behavior for actionable current-head feedback
   - keep the post-review auto-merge wait path aligned with the same stale-thread semantics so the PR does not remain blocked after auto-merge is enabled
   - keep finish output explicit about why the stale-thread-only path may continue
   - update docs in `AGENTS.md` / `docs/AGENT_RUNBOOK.md` if wording must change to match the final stale-thread behavior

3. Validate
   - add regression coverage for:
     - outdated unresolved review-thread pass path
     - actionable current-head review-thread blocker path
     - post-review auto-merge path where GitHub still reports a stale unresolved thread on an otherwise green PR
   - add at least one unaffected-caller regression for the shared review-gate surface:
     - `tests/unit/scripts/test_check_pr_review_gate.py`
   - rerun relevant finish/review-gate workflow tests plus the script surface

4. Ship (PR, checks, merge, main sync)
   - run the canonical local gate
   - close task ledgers on-branch
   - open ready PR with canonical metadata
   - complete merge through `horadus tasks finish TASK-306`

## Decisions (Timestamped)

- 2026-03-12: Follow up only on the still-live stale-thread finish gap; the earlier safe-start intake issues recorded in `artifacts/agent/temp-report-canonical-flow-issues.md` are already covered by `TASK-305`

## Risks / Foot-guns

- Over-broad stale-thread allowance can hide real current-head review feedback -> keep explicit current-head vs outdated semantics and regression-test both
- GitHub merge-blocker behavior can still diverge from CLI assumptions -> test the exact stale-thread-only path against finish-state logic
- Shared workflow change can break review-gate scripts or unaffected finish paths -> add at least one unaffected-caller regression
- Docs drift can reintroduce manual-fallback guidance after the code is fixed -> update operator docs in the same task

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_cli.py -k "finish_task_data or review_gate" -q`
- `uv run --no-sync pytest tests/unit/scripts/test_check_pr_review_gate.py -q`
- `uv run --no-sync pytest tests/workflow -q -k "finish or review_gate"`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `scripts/check_pr_review_gate.py`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
  - `docs/AGENT_RUNBOOK.md`
  - `AGENTS.md`
- Canonical example: `artifacts/agent/temp-report-canonical-flow-issues.md`
