# TASK-300: Introduce a Versioned CLI Shell and Move Legacy CLI to `v1`

## Status

- Owner: Codex
- Started: 2026-03-11
- Current state: Not started

## Goal (1-3 lines)

Create an explicit versioned CLI shell so the current externally exposed
`horadus` behavior runs from `v1`, and later `v2` work can land without mixing
legacy and new CLI code in the same package surface.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-300`)
  - current `TASK-299` follow-up scope that depends on a versioned shell first
- Runtime/code touchpoints:
  - `src/horadus_cli/`
  - `src/cli.py`
  - CLI-related tests under `tests/unit/`
  - task workflow docs that mention CLI entrypoints
- Preconditions/dependencies:
  - preserve the external `horadus` command contract exactly
  - keep this as a packaging move only, with no intentional behavior changes

## Outputs

- Expected behavior/artifacts:
  - `src/horadus_cli/app.py` acting as the top-level router
  - legacy CLI implementation moved under `src/horadus_cli/v1/`
  - package structure ready for later `src/horadus_cli/v2/` work
  - unchanged external `horadus` CLI behavior after the move
- Validation evidence:
  - parser/CLI regression coverage proving the `v1` move preserved behavior
  - local gates passing after the packaging move

## Non-Goals

- Explicitly excluded work:
  - implementing the `v2` task workflow; `TASK-299` owns that work
  - changing command names, output contracts, task workflow policy, or review logic
  - deleting legacy CLI code
  - mixing new `v2` feature work into this packaging task

## Scope

- In scope:
  - add a versioned shell layout under `src/horadus_cli/`
  - move current legacy CLI code under `src/horadus_cli/v1/`
  - route current behavior through the top-level app/router
  - update imports/tests/docs as needed to preserve behavior after the move
  - keep new files created for this packaging move at or under 300 lines
- Out of scope:
  - cutting canonical `horadus tasks ...` over to `v2`
  - changing runtime CLI semantics
  - deleting `v1`

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory current CLI entrypoints, imports, and tests that assume the unversioned layout
   - define the exact versioned package structure: shell, `v1`, and placeholder-ready `v2`
   - capture the current CLI behavior baseline before moving files
2. Implement
   - move legacy CLI implementation under `src/horadus_cli/v1/`
   - keep `src/horadus_cli/app.py` as the stable top-level router
   - update imports and entrypoints so `horadus` continues to invoke `v1`
   - avoid mixing any new `v2` behavior into the packaging move
3. Validate
   - rerun parser/CLI regression coverage for the existing external behavior
   - add targeted coverage that the router dispatches to `v1` without changing outputs
   - confirm the packaging move preserved command names, options, exit codes, and output shape
4. Ship (PR, checks, merge, main sync)
   - update task/docs surfaces required by repo policy
   - run required local gates
   - open PR, complete review/check flow, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-11: Introduce the versioned CLI shell before any `v2` implementation work so the migration boundary is explicit from the start.
- 2026-03-11: Keep `src/horadus_cli/app.py` as the stable top-level router and run current behavior through `v1`.
- 2026-03-11: Treat this as a pure compatibility-preserving packaging move; any intentional behavior change belongs in follow-up tasks, not here.
- 2026-03-11: Keep new files created for this task at or under 300 lines.

## Risks / Foot-guns

- Large file moves can hide behavioral drift -> separate packaging moves from behavior changes and validate against the current CLI baseline
- Import churn can break entrypoints or tests silently -> inventory import sites first and rerun parser/CLI coverage after the move
- The shell/router can start owning logic instead of routing only -> keep business logic in `v1` and the shell thin
- `v2` work can leak into this task -> keep `TASK-300` strictly packaging-only

## Validation Commands

- `uv run --no-sync pytest tests/unit -q -k "cli or horadus_cli"`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `src/horadus_cli/`
  - `src/cli.py`
  - `tests/unit/`
