# TASK-301: Move All Horadus CLI Functionality to `v2` and Delete `v1`

## Status

- Owner: Codex
- Started: 2026-03-11
- Current state: Not started

## Goal (1-3 lines)

After `TASK-299` cuts canonical `horadus tasks ...` over to `v2`, migrate the
remaining Horadus CLI surfaces to `src/horadus_cli/v2/`, remove
`src/horadus_cli/v1/` entirely, and leave the top-level shell depending only
on `v2`.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-301`)
  - `TASK-300` versioned shell and `v1` packaging move
  - `TASK-299` `v2` task-workflow cutover
- Runtime/code touchpoints:
  - `src/horadus_cli/app.py`
  - `src/horadus_cli/v2/`
  - `src/cli.py`
  - CLI-related tests under `tests/horadus_cli/`
  - task workflow docs that mention CLI entrypoints
- Preconditions/dependencies:
  - `TASK-299` must land first
  - canonical `horadus tasks ...` must already route to `v2`
  - temporary public `tasks-v2` must already be removed

## Outputs

- Expected behavior/artifacts:
  - `src/horadus_cli/v1/` removed from the runtime package
  - every shipped Horadus CLI command family implemented under `v2`
  - `src/horadus_cli/app.py` and `src/cli.py` with no runtime dependency on `v1`
  - docs/tests updated to the post-`v1` layout
- Validation evidence:
  - router coverage proving no runtime path still imports from `v1`
  - regression coverage that canonical `horadus tasks ...` still dispatches to
    `v2`
  - local gates passing after the cleanup

## Non-Goals

- Explicitly excluded work:
  - reintroducing `tasks-v2`
  - changing canonical `horadus tasks ...` behavior after the `TASK-299`
    cutover
  - starting new task-workflow feature work
  - imposing a repo-wide file-length policy

## Scope

- In scope:
  - inventory command families still routed through `v1`
  - re-home every supported CLI surface out of `v1`
  - delete `src/horadus_cli/v1/`
  - simplify `src/horadus_cli/app.py` and `src/cli.py` so they no longer depend on `v1`
  - update tests/docs for the post-`v1` layout
- Out of scope:
  - rebuilding the `v2` task workflow
  - reopening the transitional `tasks-v2` rollout seam
  - changing shipped task-workflow semantics beyond cleanup-driven routing

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - verify `TASK-299` already left canonical `tasks` on `v2`
   - inventory every remaining runtime import or command family that still
     depends on `v1`
   - identify the remaining legacy/triage/result shell surfaces that must move
     before `v1` can be deleted cleanly
2. Implement
   - move or re-home any still-supported CLI behavior that remains in `v1`
   - delete `src/horadus_cli/v1/`
   - simplify `src/horadus_cli/app.py`, `src/cli.py`, and top-level wrappers
     so they route exclusively through `v2`
   - remove dead compatibility branches and stale `v1` references
3. Validate
   - add regression coverage that canonical Horadus command families dispatch
     through `v2`
   - add regression coverage or architecture checks proving there are no
     shipped runtime or active-test imports from `src/horadus_cli/v1/`
   - rerun CLI regression coverage for legacy, triage, and task command
     families after the cleanup
   - verify docs describe the post-`v1` layout accurately
4. Ship (PR, checks, merge, main sync)
   - update task/docs surfaces required by repo policy
   - run required local gates
   - open PR, complete review/check flow, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-11: Treat `src/horadus_cli/v1/` as temporary migration scaffolding,
  not a permanent extra layer.
- 2026-03-11: Keep `TASK-301` separate from `TASK-299` so the `v2` cutover and
  the `v1` deletion remain independently reviewable.
- 2026-03-11: Require explicit inventory of any remaining non-task command
  families still parked in `v1` before deleting that package.

## Risks / Foot-guns

- deleting `v1` too early can strand still-supported command families ->
  inventory every remaining router target before removal
- app-level cleanup can accidentally change CLI behavior -> keep regression
  coverage on canonical `tasks` and any re-homed non-task surfaces
- dead references to `v1` can remain in docs/tests -> search for and remove
  obsolete layout references before closure

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli -q -k "cli or horadus_cli"`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `src/horadus_cli/app.py`
  - `src/horadus_cli/v1/`
  - `src/horadus_cli/v2/`
  - `src/cli.py`
  - `tests/horadus_cli/`
