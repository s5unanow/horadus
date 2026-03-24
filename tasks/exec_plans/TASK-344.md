# TASK-344: Surface review-gate wait state and deadlines in `horadus tasks finish`

## Status

- Owner: Codex automation
- Started: 2026-03-24
- Current state: In progress
- Planning Gates: Required — touching allowlisted shared workflow hotspot `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`

## Goal (1-3 lines)

Make `horadus tasks finish` emit an explicit review-gate waiting status that is
operator-visible and derived from structured review-gate fields instead of a
generic timeout-only preamble.

## Inputs

- Spec/backlog references: `tasks/CURRENT_SPRINT.md`, `TASK-344` context pack
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`, `tests/horadus_cli/v2/task_finish/test_review_window_internal.py`, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies: task branch created via `uv run --no-sync horadus tasks safe-start TASK-344 --name finish-wait-state`

## Outputs

- Expected behavior/artifacts: waiting output includes reviewer, current head, and remaining/deadline details without a misleading generic wait preamble
- Validation evidence: focused finish-path unit tests, then canonical local gates for shared workflow helpers

## Non-Goals

- Explicitly excluded work: changing review-timeout semantics, changing CI wait behavior, or redesigning the underlying PR review gate script

## Scope

- In scope: deterministic wait-line formatting inside finish review-window handling, focused regression coverage, ledger/docs updates required to close the task
- Out of scope: unrelated workflow refactors or new review-state data sources

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: synthesize the operator-facing waiting line from parsed review-gate fields in `_review_window.py`
- Rejected simpler alternative: keep depending on `summary` text from `check_pr_review_gate.py`; too brittle and still leaves the generic local preamble ambiguous
- First integration proof: targeted review-window unit test should pass with a generic review-gate summary once finish formats the wait line itself
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context) — completed
2. Implement — in progress
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-24: Keep the hotspot flat and avoid a larger refactor; add a small helper for wait-line formatting inside `_review_window.py`. (Preserves existing finish flow while making the operator-facing output deterministic.)

## Risks / Foot-guns

- Finish output order is user-facing and already regression-tested -> keep the wait line in the same phase and add a test that rejects the legacy timeout-only preamble
- Shared workflow helper changes can fan out broadly -> run the caller-aware validation pack including `make typecheck`

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/test_review_window_internal.py -v -m unit`
- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/test_review_window_recovery.py -v -m unit`
- `make agent-check`
- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks finish TASK-344`

## Notes / Links

- Spec: none; backlog/context-pack task
- Relevant modules: `tools/horadus/python/horadus_workflow/task_workflow_finish/_review_window.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
