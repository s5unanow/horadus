# TASK-296: Let Guarded Task Start Handle Task-Ledger Intake Safely

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: In progress

## Goal (1-3 lines)

Allow guarded task start to carry forward legitimate task-ledger intake edits
without forcing stash hacks or a commit on `main`, while still blocking
unrelated dirty files and preserving the overall branch-start discipline.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-296`)
- Runtime/code touchpoints: `src/horadus_cli/task_commands.py`, `tests/unit/test_cli.py`
- Preconditions/dependencies: `TASK-292` made `PROJECT_STATUS.md` non-authoritative and `TASK-295` tightened completion/merge enforcement, so task start should stay strict on unrelated changes while relaxing only the intake path

## Outputs

- Expected behavior/artifacts:
  - `safe-start` / `start` can proceed from `main` when only eligible task-ledger intake files are dirty for the target task
  - the CLI reports eligible intake files vs blocking dirty files explicitly
  - the new branch carries those eligible task-ledger edits forward without stash gymnastics
- Validation evidence:
  - focused unit coverage for clean, eligible-dirty, blocked-dirty, and conflicting-intake paths
  - full local gate before merge

## Non-Goals

- Explicitly excluded work:
  - relaxing clean-tree protections for arbitrary code or docs changes
  - changing the finish/merge workflow again

## Scope

- In scope:
  - task-start dirty-tree classification
  - task-specific intake eligibility checks
  - start/safe-start messaging and regression tests
  - agent-facing workflow docs that describe the new guarded intake behavior
- Out of scope:
  - redesigning task intake data structures
  - broad git-stash automation outside task-ledger intake

## Plan (Keep Updated)

1. Inspect current preflight/eligibility/start callers and define the intake-safe seam
2. Implement dirty-file classification plus task-specific intake allowance
3. Add regression tests for allowed and blocked paths
4. Validate and ship

## Decisions (Timestamped)

- 2026-03-10: Keep generic `tasks preflight` conservative and focus the relaxed intake path on task-specific guarded start behavior, so repo-wide cleanliness checks do not silently weaken for unrelated workflows.

## Risks / Foot-guns

- Allowing too much dirty state could mix unrelated work into new task branches -> classify only explicit task-ledger paths and report blocked files separately
- Allowing too little dirty state could leave the original stash friction unchanged -> cover both newly added uncommitted tasks and already-known live tasks with ledger-only edits

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -q`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules: `src/horadus_cli/task_commands.py`, `tests/unit/test_cli.py`
