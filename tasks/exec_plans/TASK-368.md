# TASK-368: Enforce Hotspot-Touch Debt Capture for Allowlisted Production Files

## Status

- Owner: Codex
- Started: 2026-04-12
- Current state: Done
- Planning Gates: Required — shared workflow/policy validation and material edits to allowlisted workflow hotspots

## Goal (1-3 lines)

Make planning validation fail closed when a task that declares an allowlisted
production hotspot does not record whether it reduced the hotspot, kept it
flat with rationale, or spun out a concrete cleanup follow-up.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-368`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/_docs_freshness_planning.py`, `tools/horadus/python/horadus_workflow/task_workflow_query.py`, `config/quality/code_shape.toml`
- Preconditions/dependencies: reuse the existing planning-gates validator; do not widen the code-shape allowlist or add a bypass around it

## Outputs

- Expected behavior/artifacts: repo-owned planning validation that requires a hotspot outcome marker for allowlisted production hotspots, plus updated templates/docs that show the canonical marker
- Validation evidence: workflow/docs freshness regression tests, task-query context-pack tests, and the standard workflow gates

## Non-Goals

- Explicitly excluded work: refactoring or shrinking the underlying hotspot modules as part of this task

## Scope

- In scope: code-shape hotspot detection from task file declarations, planning-artifact marker validation, context-pack/operator guidance, and regression coverage
- Out of scope: changing code-shape budgets, ratchets, or hotspot inventory semantics beyond reading the existing allowlist

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: extend the existing planning-artifact validator and context-pack reporting, using `config/quality/code_shape.toml` as the single hotspot inventory instead of introducing a second registry.
- Rejected simpler alternative: relying on narrative-only `Code Shape Gate` prose would keep the repo policy unenforced and let hotspot touches ship without a machine-checkable decision record.
- First integration proof: targeted docs-freshness and task-query tests covering allowlisted production files, ordinary production files, and oversized tests before the full local gate.
- Hotspot Outcome: reduce — `tools/horadus/python/horadus_workflow/_docs_freshness_planning.py` now fits the default function budgets, so this task removes its stale allowlist override while adding the new planning validation behavior.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Add hotspot marker requirement to planning validation and context-pack data
3. Update planning templates and operator docs with the canonical marker syntax
4. Validate with targeted suites, then run the strict local gate and completion workflow

## Decisions (Timestamped)

- 2026-04-12: Use the code-shape allowlist as the authoritative hotspot inventory so the rule cannot drift from the ratchet source.
- 2026-04-12: Require a dedicated `Hotspot Outcome` marker instead of inferring the decision from free-form gate prose.
- 2026-04-12: Remove the stale `_docs_freshness_planning.py` allowlist override once the refactor brings `_validate_planning_artifact` back under the default budgets.

## Risks / Foot-guns

- Directory-level file declarations could hide hotspot touches -> treat matching directory prefixes as hotspot-triggering rather than exact-file-only.
- Exec-plan and spec tasks could drift on where the marker belongs -> validate the authoritative planning artifact and surface the requirement in templates/docs.

## Validation Commands

- `make typecheck`
- `uv run --no-sync pytest tests/workflow/test_docs_freshness.py tests/horadus_cli/v2/test_task_query.py -v -m unit`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules: `tools/horadus/python/horadus_workflow/_docs_freshness_planning.py`, `tools/horadus/python/horadus_workflow/task_workflow_query.py`, `tools/horadus/python/horadus_workflow/code_shape.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
