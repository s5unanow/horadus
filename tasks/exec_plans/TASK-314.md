# TASK-314: Split Finish Workflow Into an Independent Package

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: Done
- Planning Gates: Required — shared workflow refactor across a large helper surface with direct test and CLI compatibility dependencies

## Goal (1-3 lines)

Replace the finish-workflow monolith with a focused package that has explicit
phase boundaries and minimal cross-module coupling, while preserving canonical
`horadus tasks finish` behavior and keeping compatibility shims intentionally thin.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-314`)
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md` shared-workflow guardrails
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_shared.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
  - `tools/horadus/python/horadus_cli/task_workflow_core.py`
  - `tools/horadus/python/horadus_cli/task_workflow_core.pyi`
  - `tests/horadus_cli/v2/task_finish/`
  - `tests/workflow/test_task_workflow.py`
- Preconditions/dependencies:
  - Preserve the public `tools.horadus.python.horadus_workflow.task_workflow_finish` import path
  - Preserve `horadus tasks finish` CLI behavior and result payloads
  - Keep compatibility with unaffected workflow callers during the migration

## Outputs

- Expected behavior/artifacts:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish/` package with focused internal modules
  - A thin package-level public surface for finish entry points and helper exports that still need compatibility
  - Updated tests aligned to the new ownership boundaries where practical
- Validation evidence:
  - Targeted finish-package unit tests
  - At least one regression test for an unaffected caller path through the compatibility layer
  - Relevant local gates/tests recorded in task notes or PR

## Non-Goals

- Explicitly excluded work:
  - Changing review-gate semantics, branch-policy rules, or task-close behavior
  - Broad repo-wide migration away from `task_workflow_core.py` beyond what this refactor requires
  - Folding unrelated cleanup from `task_repo.py`, `task_workflow_shared.py`, or other workflow areas into this task

## Scope

- In scope:
  - Convert `task_workflow_finish.py` into a package
  - Split finish logic into focused modules such as context, checks, review, merge, and orchestration
  - Reduce unnecessary cross-module dependencies inside finish logic
  - Update direct imports/tests where doing so materially improves independence
  - Keep a minimal package-level export surface for compatibility
- Out of scope:
  - Net-new workflow features
  - Refactoring unrelated workflow modules just for symmetry
  - Deleting the broader CLI compatibility facade unless all dependencies are intentionally migrated

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `task_workflow_finish` as the canonical import path by turning it into a package, with short internal module names and a thin `__init__.py`.
- Rejected simpler alternative:
  - Flat sibling files like `task_workflow_finish_context.py` reduce line count but still leave naming noise and a weaker ownership boundary than a dedicated package.
- First integration proof:
  - Current tests are already grouped by finish concerns (`test_finish_context.py`, `test_required_checks.py`, `test_review_refresh.py`, `test_review_threads.py`, `test_finish_data.py`).
- Waivers:
  - Some compatibility exports may remain at package scope during the transition if they are intentionally thin and covered by regression tests.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - Add the task intake on `main`, run guarded preflight, and start `TASK-314`.
   - Reconfirm all finish-module importers and helper patch points.
   - Map the current function groups to package modules before moving code.
2. Implement
   - Create `task_workflow_finish/` package with focused modules and package-level re-exports.
   - Move orchestration into a dedicated module and keep lower-level modules independent.
   - Update CLI compatibility surfaces and any direct imports/tests needed for the new shape.
3. Validate
   - Run targeted finish tests and at least one unaffected-caller regression path.
   - Run the relevant workflow gate subset and fix any compatibility regressions.
4. Ship (PR, checks, merge, main sync)
   - Commit task-close state on the branch, open PR, finish through the canonical workflow, and verify local `main` sync.

## Decisions (Timestamped)

- 2026-03-13: Use a `task_workflow_finish/` package instead of more flat `task_workflow_finish_*` files. (reason: keeps the public import stable while creating stronger internal boundaries)
- 2026-03-13: Treat the orchestrator as the only phase-composition module and keep lower-level finish modules as independent as practical. (reason: prevents the split from becoming a distributed monolith)

## Risks / Foot-guns

- Package split preserves every old helper export and effectively recreates the monolith at `__init__.py` -> keep `__init__.py` thin and move tests toward focused modules where practical
- Review helpers remain tightly coupled to merge or closure checks -> keep review logic dependent only on explicit inputs and shared/lifecycle helpers
- CLI compatibility patches stop propagating after helper moves -> regression-test one unaffected caller path through `task_workflow_core.py`

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-314 --name split-finish-package`
- `pytest tests/horadus_cli/v2/task_finish -v`
- `pytest tests/workflow/test_task_workflow.py -v`
- `pytest tests/horadus_cli/v2/test_task_commands.py -v`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - Backlog entry only; this exec plan is the authoritative planning artifact.
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_finish.py`
  - `tools/horadus/python/horadus_cli/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/pr_review_gate.py`
- Related prior split:
  - `tasks/exec_plans/TASK-313.md`
