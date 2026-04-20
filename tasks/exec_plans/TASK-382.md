# TASK-382: Add Task-Scoped Sprint Orientation and Test Candidates

## Status

- Owner: Codex
- Started: 2026-04-20
- Current state: In progress
- Planning Gates: Required — shared workflow/context-pack contract and task-ledger extraction behavior

## Goal (1-3 lines)

Make implement-mode `context-pack` smaller and more actionable for autonomous
callers by adding explicit task status and autonomous eligibility, task-scoped
sprint extraction, compact orientation metadata, and deterministic test
candidate hints.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` `TASK-382`,
  `docs/rfc/001-agent-context-retrieval.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/`,
  `tests/horadus_cli/v2/`, `tests/workflow/`, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies: `TASK-380` added implement mode and `TASK-381`
  added canonical task-spec resolution; caller migration stays deferred to
  `TASK-383`.

## Outputs

- Expected behavior/artifacts: implement-mode JSON exposes derived task status,
  autonomous eligibility, a compact `CURRENT_SPRINT.md` task slice, orientation
  metadata for the canonical implementation docs, and derived test candidates
  from declared paths.
- Validation evidence: targeted CLI/workflow tests, `make typecheck`, shared
  workflow validation pack, `make agent-check`, integration proof, local
  review, and `uv run --no-sync horadus tasks local-gate --full`.

## Non-Goals

- Switching agent callers to consume the new payload; that belongs to
  `TASK-383`.
- Replacing the broad default context-pack output.
- Adding retrieval index infrastructure or policy-doc front matter migration.

## Scope

- In scope: implement-mode payload expansion, sprint/task metadata shaping,
  deterministic test-candidate derivation, and matching docs/tests.
- Out of scope: general backlog triage changes, finish-mode retrieval, and
  unrelated workflow policy edits.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: extend implement-mode payload with
  focused helper data derived from existing task ledgers and declared paths,
  while keeping default mode output unchanged.
- Rejected simpler alternative: embedding larger raw `CURRENT_SPRINT.md` or
  whole-doc orientation text would satisfy the surface contract but would
  reintroduce the noise RFC-001 is trying to remove.
- First integration proof:
  `uv run --no-sync horadus tasks context-pack TASK-382 --mode implement --format json`
  plus targeted CLI/workflow tests.
- Hotspot Outcome: keep-flat-with-rationale — avoid material edits to the
  allowlisted workflow hotspots by adding focused context-pack helpers and only
  touching existing orchestrators where necessary to thread the new payload.
- Waivers: none planned; if an integration proof is unnecessary for a narrowed
  change set, record the N/A explicitly before ship.

## Plan (Keep Updated)

1. Preflight (eligibility, context-pack, exec plan, guarded start)
2. Implement task metadata, sprint orientation, and test-candidate helpers
3. Add regression tests and update operator/RFC docs
4. Validate with targeted suites, local review, and full local gate
5. Ship through `horadus tasks finish` and strict lifecycle verification

## Decisions (Timestamped)

- 2026-04-20: Use an exec plan instead of a new task spec because the task is
  implementation-ready and planning gates are needed mainly for shared
  workflow/hotspot control.
- 2026-04-20: Keep hotspot debt flat by preferring new helper modules or small
  helper additions over growing allowlisted workflow modules with unrelated
  parsing logic.

## Risks / Foot-guns

- Implement-mode payload changes can silently break existing callers or tests ->
  keep default mode unchanged and add explicit implement-mode regression tests.
- Sprint parsing can drift from the live ledger format -> derive a narrow slice
  from the existing task-ledger parser behavior instead of ad hoc text search
  where possible.
- Derived test candidates could become noisy or misleading -> label each match
  with a deterministic `match_reason` and keep the heuristics bounded to
  declared task paths.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_query_context_pack_modes.py tests/horadus_cli/v2/test_task_query.py tests/horadus_cli/v2/test_task_repo.py tests/workflow/test_task_workflow.py -v -m unit`
- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- RFC: `docs/rfc/001-agent-context-retrieval.md`
- Relevant modules:
  `tools/horadus/python/horadus_workflow/task_workflow_context_pack_implement.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_query.py`,
  `tools/horadus/python/horadus_workflow/task_repo.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
