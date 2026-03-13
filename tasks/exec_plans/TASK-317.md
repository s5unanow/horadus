# TASK-317: Decompose `review.py` Into Focused Internal Modules

## Status

- Owner:
- Started: 2026-03-13
- Current state: Done
- Planning Gates: Required — shared finish-workflow review semantics have multiple direct importers and extensive monkeypatch-based regression coverage

## Goal (1-3 lines)

Break `tools/horadus/python/horadus_workflow/task_workflow_finish/review.py`
into smaller focused internal modules while preserving finish behavior,
current-head versus outdated-review semantics, and the current public helper
surface.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-317`)
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md` shared-workflow guardrails
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/review.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/__init__.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/__init__.pyi`
  - `tools/horadus/python/horadus_cli/task_finish.py`
  - `tools/horadus/python/horadus_cli/task_workflow_core.py`
  - `tests/horadus_cli/v2/task_finish/test_helpers.py`
  - `tests/horadus_cli/v2/task_finish/test_review_threads.py`
  - `tests/horadus_cli/v2/task_finish/test_review_refresh.py`
  - `tests/horadus_cli/v2/task_finish/test_finish_data.py`
- Preconditions/dependencies:
  - Keep helper names, outputs, and finish-loop semantics stable
  - Preserve compatibility for direct imports and monkeypatching through the finish package / CLI compatibility layers
  - Avoid policy changes in current-head versus outdated review handling

## Outputs

- Expected behavior/artifacts:
  - Focused internal finish-review modules grouped by responsibility
  - Compatibility-preserving `review.py` facade that still exports the current helper names
  - Regression tests proving unchanged finish behavior and import/patch stability
- Validation evidence:
  - Targeted task-finish review tests pass unchanged or with only ownership-aligned updates
  - `review_gate_data(...)` behavior remains stable across current-head, stale-thread, and fresh-review flows

## Non-Goals

- Explicitly excluded work:
  - Any change to merge policy, review timeout policy, or fresh-review request policy
  - Rewording user-facing finish output or blocker text
  - Unrelated cleanup in the finish workflow package

## Scope

- In scope:
  - Extract review-gate command execution/parsing into a dedicated module
  - Extract review-thread fetching/formatting and stale-thread resolution into dedicated modules
  - Extract fresh-review request / pre-review stale-context detection into a dedicated module
  - Keep or move orchestration into a thinner review-window focused module while preserving exports
- Out of scope:
  - Changing CLI command wiring or the finish orchestrator contract
  - Changing the task workflow package export surface
  - Changing test assertions that encode current behavior unless the move requires narrowly targeted compatibility coverage

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `review.py` as a compatibility re-export facade and move implementation into focused internal modules.
- Rejected simpler alternative:
  - Keeping one large `review.py` with section comments would not improve testable ownership or current-head/outdated-state readability enough.
- First integration proof:
  - The existing `tests/horadus_cli/v2/task_finish/` suite already captures the behavior that must remain unchanged.
- Waivers:
  - Small compatibility indirection is acceptable if it preserves monkeypatch behavior and public imports.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Treat this as a new live task instead of reusing the earlier finish-review tasks. (reason: task ids are global and the user requested repo-policy compliance)
- 2026-03-13: Preserve `review.py` as the stable external surface and move only the internal ownership boundaries. (reason: tests and compatibility imports patch helpers through the existing module names)
- 2026-03-13: Keep the split responsibility-aligned rather than introducing broader package cleanup. (reason: the user explicitly asked for a behavior-preserving refactor only)

## Risks / Foot-guns

- Monkeypatch propagation breaks after helpers move -> keep a compatibility facade that forwards attribute writes to owning modules
- Output/order drift in finish-loop lines -> preserve call order and reuse existing message construction
- Review-thread parsing behavior changes accidentally -> keep parser code behavior identical and validate with the existing negative-payload tests

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-317`
- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/test_helpers.py -q`
- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/test_review_threads.py -q`
- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/test_review_refresh.py -q`
- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/test_finish_data.py -q`
- `uv run --no-sync ruff check tools/horadus/python/horadus_workflow/task_workflow_finish tests/horadus_cli/v2/task_finish`

## Notes / Links

- Spec:
  - Backlog entry only; this exec plan is the authoritative planning artifact.
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/review.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/__init__.py`
  - `tools/horadus/python/horadus_cli/task_workflow_core.py`
  - `tests/horadus_cli/v2/task_finish/test_review_threads.py`
  - `tests/horadus_cli/v2/task_finish/test_review_refresh.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
