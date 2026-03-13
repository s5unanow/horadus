# TASK-313: Split `task_workflow_core.py` Into Focused Workflow Modules

## Status

- Owner:
- Started: 2026-03-13
- Current state: Not started
- Planning Gates: Required — shared workflow ownership split with many existing callers and regression risk across task CLI entry points

## Goal (1-3 lines)

Break `tools/horadus/python/horadus_workflow/task_workflow_core.py` into
focused workflow modules that match the already-split CLI command ownership,
without changing the canonical `horadus tasks ...` behavior or stranding
shared helpers behind a new accidental monolith.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-313`)
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md` shared-workflow guardrails
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_cli/task_preflight.py`
  - `tools/horadus/python/horadus_cli/task_workflow.py`
  - `tools/horadus/python/horadus_cli/task_finish.py`
  - `tools/horadus/python/horadus_cli/task_ledgers.py`
  - `tools/horadus/python/horadus_cli/task_lifecycle.py`
  - `tools/horadus/python/horadus_cli/task_friction.py`
  - `tools/horadus/python/horadus_cli/task_query.py`
  - `tools/horadus/python/horadus_cli/task_shared.py`
- Preconditions/dependencies:
  - Preserve the current CLI registration in `tools/horadus/python/horadus_cli/task_commands.py`
  - Respect existing tests that import `tools.horadus.python.horadus_cli.task_workflow_core`
  - Keep repo-workflow behavior stable while moving helpers behind focused ownership modules

## Outputs

- Expected behavior/artifacts:
  - Focused workflow modules under `tools/horadus/python/horadus_workflow/`
  - Compatibility-preserving exports for the thin CLI wrappers and tests
  - Updated tests that follow the new ownership boundaries instead of a single monolithic target
- Validation evidence:
  - Targeted CLI/workflow unit tests for each moved command area
  - At least one regression test covering an unaffected caller path after shared helpers move
  - Relevant local gate/test commands recorded in the task notes or PR

## Non-Goals

- Explicitly excluded work:
  - Changing the user-facing `horadus tasks ...` command contract
  - Rewriting review-gate semantics, preflight policy, or task-ledger rules beyond compatibility-preserving extraction
  - Folding unrelated cleanup from `task_repo.py`, `docs_freshness.py`, or other large workflow files into this task

## Scope

- In scope:
  - Define module boundaries before code motion
  - Move code into ownership-aligned workflow modules
  - Preserve or intentionally rehome shared constants, dataclasses, and helper functions
  - Update CLI wrapper imports and tests to match the new layout
  - Leave either a thin compatibility facade at `task_workflow_core.py` or remove it only after all imports are migrated
- Out of scope:
  - Net-new workflow features
  - Behavior changes that would require separate task acceptance criteria
  - Test-suite reorganization outside files directly coupled to the split

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Split by current command ownership seams already exposed in the CLI wrappers, then keep a narrow compatibility layer until direct imports are migrated.
- Rejected simpler alternative:
  - Keeping `task_workflow_core.py` intact and only adding section comments does not reduce coupling, import sprawl, or test patching pressure.
- First integration proof:
  - `tools/horadus/python/horadus_cli/task_preflight.py`,
    `task_finish.py`, `task_lifecycle.py`, `task_ledgers.py`,
    `task_query.py`, `task_friction.py`, and `task_workflow.py`
    already define the intended ownership seams on the CLI side.
- Waivers:
  - A temporary compatibility facade is acceptable during the migration if it is intentionally thin and covered by regression tests.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - Run guarded task start for `TASK-313`.
   - Reconfirm all current importers of `task_workflow_core.py`.
   - Group tests by command area so the split is validated incrementally.
2. Implement
   - Introduce focused workflow modules, likely around:
     - shared/runtime helpers and constants
     - preflight/start/eligibility
     - finish/review-gate
     - lifecycle/local-gate
     - ledger-close helpers
     - query/context-pack helpers
     - friction reporting
   - Re-export from a compatibility surface only where needed.
   - Update CLI wrapper imports and direct-test imports module by module.
3. Validate
   - Run targeted workflow and CLI tests for each moved area.
   - Add or retain one regression test for an unaffected caller path.
   - Run broader workflow gate/tests once the split settles.
4. Ship (PR, checks, merge, main sync)
   - Open one task PR with the task-close state on head.
   - Finish through the canonical workflow and verify local `main` sync.

## Decisions (Timestamped)

- 2026-03-13: Treat the split as a shared-workflow refactor with planning gates required because many CLI entry points and tests depend on this module directly. (reason: helper moves can easily break unrelated commands)
- 2026-03-13: Use the existing CLI wrapper files as the first-pass module-boundary map instead of inventing a new taxonomy. (reason: those wrappers already reflect intended command ownership)
- 2026-03-13: Preserve a thin compatibility layer if needed during migration rather than forcing a one-shot import cutover. (reason: reduces blast radius and keeps tests shippable in smaller moves)

## Risks / Foot-guns

- Shared helpers get copied into multiple modules instead of being intentionally rehomed -> define a single shared helper home before moving command-specific code.
- Tests keep importing the old monolith and hide boundary regressions -> migrate test imports by ownership area, not only production imports.
- Compatibility facade remains large and permanent -> set an explicit expectation that the facade must be thin or deleted by task close.
- Finish/review-gate helpers are tightly interleaved with lifecycle and subprocess helpers -> move incrementally and keep targeted regression tests around current-head/current-window semantics.

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-313`
- `pytest tests/horadus_cli/v2/test_task_preflight.py -v`
- `pytest tests/horadus_cli/v2/task_finish -v`
- `pytest tests/horadus_cli/v2/test_task_lifecycle.py -v`
- `pytest tests/horadus_cli/v2/test_task_ledgers.py -v`
- `pytest tests/horadus_cli/v2/test_task_query.py -v`
- `pytest tests/horadus_cli/v2/test_task_friction.py -v`
- `pytest tests/workflow/test_task_workflow.py -v`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - Backlog entry only; this exec plan is the authoritative planning artifact.
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_cli/task_preflight.py`
  - `tools/horadus/python/horadus_cli/task_workflow.py`
  - `tools/horadus/python/horadus_cli/task_finish.py`
  - `tools/horadus/python/horadus_cli/task_ledgers.py`
  - `tools/horadus/python/horadus_cli/task_lifecycle.py`
  - `tools/horadus/python/horadus_cli/task_query.py`
  - `tools/horadus/python/horadus_cli/task_friction.py`
  - `tools/horadus/python/horadus_cli/task_shared.py`
- Known dependent tests/import surfaces:
  - `tests/horadus_cli/v2/test_task_preflight.py`
  - `tests/horadus_cli/v2/task_finish/test_finish_data.py`
  - `tests/horadus_cli/v2/task_finish/test_review_threads.py`
  - `tests/horadus_cli/v2/test_task_lifecycle.py`
  - `tests/horadus_cli/v2/test_task_ledgers.py`
  - `tests/horadus_cli/v2/test_task_query.py`
  - `tests/horadus_cli/v2/test_task_friction.py`
  - `tests/workflow/test_task_workflow.py`
