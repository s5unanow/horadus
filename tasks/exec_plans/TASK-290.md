# TASK-290: Make `horadus tasks finish` Fail Fast When CI Is Red After Review Timeout

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: In Progress

## Goal (1-3 lines)

Make the task-finish lifecycle report failed required CI promptly once the
review gate has cleared, instead of appearing to hang until a later timeout
path while the current PR head is already red.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-290`)
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `src/horadus_cli/task_commands.py`
  - `tests/unit/test_cli.py`
  - `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies:
  - `TASK-257` completed and exposed the follow-up bug during finish-time CI
  - Finish-flow changes are shared-workflow changes and require caller-aware
    regression coverage

## Outputs

- Expected behavior/artifacts:
  - Finish flow re-checks required CI state after the review gate clears
  - Red-check state is surfaced immediately with a concrete blocker
  - Docs reflect the corrected failed-CI finish behavior
- Validation evidence:
  - Focused unit tests for finish-flow red/green paths
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - Redesigning the entire review-gate timeout policy
  - Changing merge policy for genuinely green PRs
  - Broader task-start workflow fixes beyond the specific failed-CI finish bug

## Scope

- In scope:
  - Finish-flow failed-CI detection after review gate completion
  - Regression coverage for affected and unaffected finish paths
  - Agent-facing docs for the corrected blocker behavior
- Out of scope:
  - New review-signal semantics
  - General PR-status polling refactors not needed for this bug

## Plan (Keep Updated)

1. Inspect current finish-flow sequencing around review, checks, and merge waits
2. Implement fail-fast CI-red detection after review gate completion
3. Add regression tests for red-CI and unaffected green flows
4. Validate locally and complete the task lifecycle

## Decisions (Timestamped)

- 2026-03-10: Treat this as a shared-workflow bug because it affects the
  canonical `horadus tasks finish` lifecycle rather than one task-specific PR.

## Risks / Foot-guns

- Re-checking CI at the wrong point could regress silent-timeout allow merges ->
  preserve the existing green path and add an unaffected success regression test.
- GitHub check-rollup state can lag slightly -> fail fast only when the current
  required-check query concretely reports failure, not just "not green yet".

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -k "finish_task_data and (review or checks or merge)" -q`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Triggering incident: `TASK-257` finish flow stayed in the timeout path instead
  of reporting failed CI promptly after the PR checks turned red.
