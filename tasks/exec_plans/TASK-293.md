# TASK-293: Decouple CLI Tests from Live Task IDs

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: In progress

## Goal (1-3 lines)

Remove CLI test dependence on whichever task ids happen to be live in the repo.
Keep parser and command coverage real by using stable synthetic repo layouts
instead of mutable `tasks/BACKLOG.md` state on `main`.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-293`)
- Runtime/code touchpoints: `src/horadus_cli/task_repo.py`, `src/horadus_cli/task_commands.py`, `scripts/task_context_pack.sh`
- Preconditions/dependencies: `TASK-292` and `TASK-294` changed live/archive task lookup semantics, so tests must stop assuming a specific open task remains live forever

## Outputs

- Expected behavior/artifacts:
  - direct CLI tests resolve open/archive task records from a stable synthetic repo layout
  - shell wrapper tests validate argument forwarding without invoking live repo task data
  - closing a live task no longer forces unrelated CLI test fixture rewrites
- Validation evidence:
  - focused `pytest` runs for CLI and script tests
  - local gate before shipping

## Non-Goals

- Explicitly excluded work:
  - changing task lookup behavior itself
  - `safe-start` / preflight ergonomics (`TASK-296`)

## Scope

- In scope:
  - shared test helper(s) for synthetic task ledgers
  - migrating fragile tests in `tests/unit/test_cli.py`
  - decoupling `scripts/task_context_pack.sh` wrapper tests from live repo state
- Out of scope:
  - broader fixture rewrites outside the Horadus task CLI surfaces
  - converting all task-repo tests to a separate package/module if a local helper is enough

## Plan (Keep Updated)

1. Inventory the remaining live-task-id test dependencies
2. Add a stable synthetic repo helper and switch fragile tests to it
3. Validate focused tests and local gate
4. Ship and close the task

## Decisions (Timestamped)

- 2026-03-10: Use a synthetic temp repo layout for repo-backed CLI behavior tests instead of mocking away parsing entirely, so task parser coverage still follows real markdown shapes.

## Risks / Foot-guns

- Over-mocking could hide parser drift -> keep direct `task_record` / `handle_show` / `handle_context_pack` coverage reading real markdown in temp repos
- Touching broad test files can cause accidental regressions -> keep helper narrow and target only the fragile tests that depend on live repo state

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -q`
- `uv run --no-sync pytest tests/unit/scripts/test_task_context_pack.py -q`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules: `src/horadus_cli/task_repo.py`, `src/horadus_cli/task_commands.py`, `scripts/task_context_pack.sh`
