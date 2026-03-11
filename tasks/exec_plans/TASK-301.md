# TASK-301: Retire `v1` and Leave the App Router Pointing at `v2`

## Status

- Owner: Codex
- Started: 2026-03-11
- Current state: Not started

## Goal (1-3 lines)

After `TASK-299` cuts canonical `horadus tasks ...` over to `v2`, remove the
temporary `src/horadus_cli/v1/` package and leave the top-level app router
pointing at `v2` for the task workflow with no remaining runtime dependence on
`v1`.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-301`)
  - `TASK-300` versioned shell and `v1` packaging move
  - `TASK-299` `v2` task-workflow cutover
- Runtime/code touchpoints:
  - `src/horadus_cli/app.py`
  - `src/horadus_cli/v1/`
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
  - `src/horadus_cli/app.py` routing canonical `horadus tasks ...` to `v2`
  - any still-supported non-task CLI surfaces re-homed out of `v1`
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
  - re-home supported runtime behavior out of `v1` where required
  - delete `src/horadus_cli/v1/`
  - simplify `src/horadus_cli/app.py` so it no longer depends on `v1`
  - update tests/docs for the post-`v1` layout
- Out of scope:
  - rebuilding the `v2` task workflow
  - reopening the transitional `tasks-v2` rollout seam
  - changing shipped task-workflow semantics beyond cleanup-driven routing

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - verify `TASK-299` already left canonical `tasks` on `v2` and removed
     `tasks-v2`
   - inventory every remaining runtime import or command family that still
     depends on `v1`
   - decide which supported surfaces must be re-homed before `v1` can be
     deleted cleanly
2. Implement
   - move or re-home any still-supported CLI behavior that remains in `v1`
   - delete `src/horadus_cli/v1/`
   - simplify `src/horadus_cli/app.py` so the router points to `v2` for task
     workflow and has no runtime dependency on `v1`
   - remove dead compatibility branches and stale `v1` references
3. Validate
   - add regression coverage that canonical `horadus tasks ...` dispatches to
     `v2`
   - add regression coverage or architecture checks proving there are no
     shipped runtime imports from `src/horadus_cli/v1/`
   - rerun CLI regression coverage for any non-task command families re-homed
     during the cleanup
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
