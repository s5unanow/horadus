# TASK-365: Add Retrieval Behavior Evals for RFC-001 Context Surfaces

## Status

- Owner: Codex
- Started: 2026-04-21
- Current state: In progress
- Planning Gates: Required — shared workflow/context-retrieval contract and policy surface

## Goal (1-3 lines)

Add deterministic behavior evals for RFC-001 implement-mode retrieval so the
CLI’s include/exclude rules and minimal-context contract are measured the same
way as other high-risk workflow behavior.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` `TASK-365`,
  `tasks/specs/288-rfc-001-implementation-breakdown.md`,
  `docs/rfc/001-agent-context-retrieval.md`
- Runtime/code touchpoints: `src/eval/`, `tools/horadus/python/horadus_workflow/`,
  `tools/horadus/python/horadus_cli/`, `tests/horadus_cli/v2/`,
  `tests/unit/eval/`, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies: `TASK-380`, `TASK-381`, and `TASK-382` already
  landed the Phase 1 implement-mode context-pack surface and retrieval metadata.

## Outputs

- Expected behavior/artifacts: retrieval-focused behavior eval cases for
  implement-mode context-pack include/exclude rules and at least one
  minimal-context contract, plus behavior artifacts that record retrieval mode,
  phase, and authoritative-source basis.
- Validation evidence: targeted eval/CLI/workflow tests, `make typecheck`,
  shared-workflow validation pack, pre-push local review, `make agent-check`,
  integration proof, and `uv run --no-sync horadus tasks local-gate --full`.

## Non-Goals

- Switching autonomous callers to implement mode; that belongs to `TASK-383`.
- Introducing local or hosted retrieval indexing.
- Broadening the default context-pack contract beyond retrieval-eval metadata.

## Scope

- In scope: retrieval behavior-eval cases, artifact metadata additions needed
  to express the retrieval contract, and operator docs for when the suite must
  run.
- Out of scope: new retrieval modes, policy-doc front matter migration, and
  unrelated workflow caller rewiring.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: extend the existing behavior-eval
  harness and exercise implement-mode context-pack through synthetic task-repo
  fixtures rather than introducing a second retrieval-specific test runner.
- Rejected simpler alternative: relying only on unit tests around helper
  functions would check parser details but would not produce the reviewable eval
  artifact or measure the end-to-end retrieval contract.
- First integration proof:
  `uv run --no-sync horadus tasks context-pack TASK-365 --mode implement --format json`
  plus the targeted eval/CLI/workflow suites.
- Hotspot Outcome: keep-flat-with-rationale — avoid material edits to the
  allowlisted workflow hotspots by placing the new retrieval behavior logic in
  focused eval helpers and only threading minimal metadata through the existing
  artifact and context-pack surfaces.
- Waivers: none planned.

## Plan (Keep Updated)

1. Preflight (context-pack, exec plan, guarded start)
2. Add retrieval behavior-eval helpers/cases and artifact metadata
3. Add regression tests and runbook updates
4. Validate with targeted suites, local review, and full local gate
5. Ship through `horadus tasks finish` and strict lifecycle verification

## Decisions (Timestamped)

- 2026-04-21: Use an exec plan instead of a short spec because the task is
  implementation-ready and the main planning need is shared-workflow/retrieval
  gate control.
- 2026-04-21: Keep the retrieval evals deterministic by using synthetic
  task-repo fixtures and the existing implement-mode context-pack entry point.

## Risks / Foot-guns

- Retrieval evals could become brittle against incidental doc wording changes ->
  assert source inclusion/exclusion reasons and compact payload shape instead of
  snapshotting full JSON payloads.
- Behavior artifacts could grow ad hoc metadata fields -> add a small
  structured contract for retrieval provenance rather than embedding loose
  strings in per-case evidence only.
- Shared workflow helper edits can break unaffected callers -> run the
  caller-aware validation pack and keep at least one unaffected implement-mode
  caller regression in coverage.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/test_behavior.py tests/horadus_cli/v2/test_task_query_context_pack_contract.py tests/horadus_cli/v2/test_task_query_context_pack_implement_output.py tests/horadus_cli/v2/test_task_query_context_pack_modes.py -v -m unit`
- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `uv run --no-sync horadus tasks local-review --format json`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- RFC: `docs/rfc/001-agent-context-retrieval.md`
- Relevant modules:
  `src/eval/behavior.py`,
  `src/eval/behavior_cases.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_context_pack_implement.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_context_pack_implement_support.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
