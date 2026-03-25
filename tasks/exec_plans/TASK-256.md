# TASK-256: Enforce the Task Completion Contract for Tests, Docs, and Gate Re-Runs

## Status

- Owner: Codex
- Started: 2026-03-25
- Current state: In progress
- Planning Gates: Required — shared workflow completion-contract change across CLI, docs, and tests

## Goal (1-3 lines)

Make the remaining task-completion expectations explicit and task-aware. The
workflow should keep `horadus tasks local-gate --full` as the canonical strict
gate while surfacing when targeted tests, integration proof, docs updates, and
documented N/A handling are still required.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-256`)
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tests/horadus_cli/v2/test_task_query_validation_packs.py`
  - `tests/horadus_cli/v2/test_task_query.py`
  - `tests/workflow/test_repo_workflow.py`
  - `tests/workflow/test_task_workflow.py`
- Preconditions/dependencies:
  - preserve `horadus tasks local-gate --full` as the single canonical strict
    gate
  - keep caller-aware validation packs aligned with any new completion-contract
    recommendations
  - avoid inventing a second workflow policy surface for task completion

## Outputs

- Expected behavior/artifacts:
  - `horadus tasks context-pack` surfaces a structured completion contract that
    separates enforced workflow steps from still-social expectations
  - completion guidance explicitly covers targeted tests, integration-gate
    applicability, docs updates, and documented N/A handling
  - workflow policy helpers expose the same contract for doc-freshness and test
    parity
- Validation evidence:
  - targeted workflow/query tests for the completion-contract helper output
  - `make typecheck`
  - `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Adding a new task-finish metadata file or separate validation manifest
- Replacing `horadus tasks finish` with a stricter second completion command
- Enforcing runtime/business-logic validation rules unrelated to workflow
  completion

## Scope

- In scope:
  - define a repo-owned completion-contract helper for workflow guidance
  - teach `context-pack` to show task-aware validation/docs/N/A expectations
  - update AGENTS/runbook guidance to distinguish enforced vs social
    expectations
  - add regression coverage for both required and N/A-style paths
- Out of scope:
  - changing review-window semantics or merge-policy logic
  - altering the full local gate step inventory itself
  - introducing monthly planning/process changes outside this task’s contract

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: extend the existing workflow policy/query surfaces instead
  of creating a separate completion-policy engine or task manifest format.
- `Anti-Abstraction Gate`: keep the completion contract as a small repo-owned
  helper with deterministic path-based recommendations; do not add a plugin
  system for a fixed set of workflow obligations.
- `Integration-First Gate`:
  - Validation target: `context-pack` output, workflow policy helpers, and doc
    guidance all agree on the same completion contract.
  - Exercises: required targeted-test guidance, integration-gate applicability,
    docs-update expectations, and at least one documented N/A path.
- `Code Shape Gate`: Not triggered — the planned edits stay in existing shared
  workflow modules without materially expanding an allowlisted hotspot.
- `Determinism Gate`: Triggered — task-aware completion guidance must derive
  deterministically from repo-owned task metadata rather than operator memory.
- `LLM Budget/Safety Gate`: Not applicable — no LLM runtime path changes.
- `Observability Gate`: Triggered — the contract must make it clear which
  obligations are already enforced and which still require human confirmation.

## Shared Workflow/Policy Change Checklist

- Callers/config that depend on the current completion-contract guidance:
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tests/workflow/test_repo_workflow.py`
  - `tests/workflow/test_task_workflow.py`
  - `tests/horadus_cli/v2/test_task_query.py`
  - `tests/horadus_cli/v2/test_task_query_validation_packs.py`
- Unaffected-caller regression target:
  - preserve the existing caller-aware validation-pack behavior for shared
    helper tasks while layering the completion-contract output on top

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - add one workflow-policy helper that describes enforced steps, required
    expectations, and N/A recording guidance, then surface it in
    `context-pack` and docs
  - keep `make agent-check` plus `horadus tasks local-gate --full` as the
    baseline validation pair
  - add integration-gate recommendations only when the task’s declared files
    indicate integration-covered or push/PR workflow surfaces
- Rejected simpler alternative:
  - updating docs alone would leave `context-pack` suggested validation drift
    unresolved and keep the contract partly implicit at execution time
- First integration proof:
  - targeted tests show the new completion-contract helper and `context-pack`
    output agree before running the broader workflow gates
- Waivers:
  - use documented N/A guidance instead of hard-enforcing every task-specific
    proof inside `horadus tasks finish`; this task is about making the contract
    explicit and aligned, not introducing a new state-tracking subsystem

## Plan (Keep Updated)

1. Add the repo-owned completion-contract helper and task-aware applicability
   checks
2. Surface that contract through `context-pack`
3. Update AGENTS/runbook/repo-workflow guidance to match the helper
4. Add regression tests for required and N/A-style paths
5. Run targeted tests, then `make typecheck`, `make agent-check`, and the full
   local gate
6. Close ledgers and finish the task lifecycle through the Horadus workflow

## Decisions (Timestamped)

- 2026-03-25: Keep `horadus tasks local-gate --full` as the only canonical
  strict local gate; task-aware recommendations should layer on top of it.
- 2026-03-25: Use the task’s declared file paths to drive integration/docs
  applicability because that metadata already feeds `context-pack` and remains
  deterministic.

## Risks / Foot-guns

- Guidance drift between repo docs and workflow helper output -> update the
  shared policy helper and reuse it from the query surface
- Over-prescribing integration proof for unrelated tasks -> scope the trigger
  to integration-covered and push/PR workflow paths only
- Adding another partially overlapping validation list -> keep baseline
  validation commands unchanged and append only truly task-aware additions

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-256`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make typecheck`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Backlog entry: `tasks/BACKLOG.md`
- Canonical planning example: `tasks/specs/275-finish-review-gate-timeout.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
