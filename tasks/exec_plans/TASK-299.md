# TASK-299: Build an Isolated `v2` Task Workflow and Cut Over from `tasks-v2`

## Status

- Owner: Codex
- Started: 2026-03-11
- Current state: Not started

## Goal (1-3 lines)

After `TASK-300` lands the versioned CLI shell, build a real `v2`
implementation under `src/horadus_cli/v2/`, expose it temporarily as
`horadus tasks-v2 ...` for parity validation, then route canonical
`horadus tasks ...` behavior through `v2` and remove the temporary
`tasks-v2` surface.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-299`)
  - review findings against `TASK-297`
  - `TASK-300` versioned CLI shell and `v1` migration work
  - current shipped finish/lifecycle recovery behavior captured by
    `TASK-289` and `TASK-291`, which must remain part of the canonical
    baseline after the cutover
- Runtime/code touchpoints:
  - `src/horadus_cli/app.py`
  - new `src/horadus_cli/v2/` modules
  - new `tests/unit/*v2*.py` coverage
  - task workflow docs that mention command entrypoints
- Preconditions/dependencies:
  - `TASK-300` must land first
  - legacy CLI behavior is routed through `src/horadus_cli/v1/`
  - the currently shipped `horadus tasks ...` behavior is the parity baseline
  - `tasks-v2` is allowed only as a temporary migration surface inside this
    task and must not survive the final cutover state

## Outputs

- Expected behavior/artifacts:
  - temporary `horadus tasks-v2 ...` routing to `src/horadus_cli/v2/` during
    parity validation
  - canonical `horadus tasks ...` routed through `src/horadus_cli/v2/`
  - real `src/horadus_cli/v2/` owner modules for query, preflight/start, ledgers, finish,
    lifecycle, friction, process helpers, and workflow composition
  - separate `v2` behavior tests outside the legacy CLI test file
  - a scoped 300-line cap respected by every new `v2` Python file
  - canonical `horadus tasks finish` behavior preserved across the cutover,
    including rerun-from-`main` recovery and already-`MERGED` convergence
  - an explicit parity matrix naming the canonical `horadus tasks`
    subcommands that must remain behavior-compatible across the cutover
- Validation evidence:
  - parser/routing coverage for canonical `horadus tasks ...`
  - parity checks against representative `tasks` vs temporary `tasks-v2`
    scenarios before the cutover
  - architecture checks proving no `v2` monolith or pure shim layer was added
  - required local gate success before merge

## Non-Goals

- Explicitly excluded work:
  - introducing the versioned CLI shell itself; `TASK-300` owns that move
  - repackaging legacy CLI code into `v1`; `TASK-300` owns that move
  - deleting `v1` in this task
  - imposing a repo-wide file-length policy
  - large opportunistic cleanup in unrelated CLI modules

## Scope

- In scope:
  - expose the isolated `v2` implementation temporarily as
    `horadus tasks-v2 ...`
  - route canonical `horadus tasks ...` through the isolated `v2`
    implementation on the versioned shell after parity is proven
  - implement modular `v2` task workflow modules under `src/horadus_cli/v2/`
  - add separate `v2` tests and parity fixtures/checks
  - document the temporary migration seam and the final cutover/removal path
  - enforce the 300-line cap for new `v2` Python files
  - define one explicit parity matrix for:
    - `preflight`
    - `start`
    - `safe-start`
    - `context-pack`
    - `close-ledgers`
    - `local-gate`
    - `lifecycle`
    - `record-friction`
    - `summarize-friction`
    - `finish`
  - preserve the currently shipped `finish` recovery behavior captured by
    `TASK-289` and `TASK-291`
  - enforce that `src/horadus_cli/v2/` does not import runtime behavior from
    `src/horadus_cli/v1/`
  - remove the temporary `tasks-v2` command family before closing the task
- Out of scope:
  - removing legacy task workflow code
  - reworking the `v1` packaging move
  - repo-wide test refactors or line-cap enforcement

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - verify the current `horadus tasks ...` behavior baseline after `TASK-300`
   - confirm the exact command families and fixture paths that the `v2`
     cutover must preserve
   - define the temporary `tasks-v2` parser/routing seam and the final removal
     point
   - write down the parity matrix for canonical `horadus tasks ...`
   - identify the minimum app-level routing change needed to move canonical
     `tasks` off `v1` and onto `v2`
2. Implement
   - keep the public `tasks` parser surface stable while introducing a
     temporary `tasks-v2` route to `v2`
   - build real `v2` owner modules for:
     - shared types/constants
     - process helpers
     - query commands
     - preflight/start
     - ledgers
     - finish
     - lifecycle
     - friction
     - cross-domain workflow composition
   - keep `v2` self-owned; do not import command behavior from `v1`
   - preserve the currently shipped finish recovery behavior:
     - rerun from `main` with explicit task id
     - converge cleanly when the PR is already merged
   - keep each new `v2` Python file at or under 300 lines
   - avoid a compatibility-core dump file and avoid pure re-export shims
   - after parity is proven, flip canonical `tasks` to `v2`, delete
     `tasks-v2`, and leave `app.py` routing canonical `tasks` to `v2`
3. Validate
   - add parser/routing tests that temporary `tasks-v2` dispatches to `v2`
     before the cutover
   - add direct owner-module tests for `v2`
   - add representative parity checks between `tasks` and temporary `tasks-v2`
     for every parity-locked subcommand in scope before the cutover
   - add parser/routing tests that canonical `horadus tasks ...` dispatches
     to `v2` after the cutover and that `tasks-v2` no longer exists
   - add finish-path regressions for:
     - branch-drift rerun from `main`
     - already-merged PR convergence
   - add an architecture guard that fails if any new `v2` Python file exceeds
     300 lines
   - add an architecture guard that fails on direct `v2` imports from `v1`
   - verify docs still describe only `horadus tasks ...` as canonical after
     this task
4. Ship (PR, checks, merge, main sync)
   - update task/docs surfaces required by repo policy
   - run required local gates
   - open PR, complete review/check flow, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-11: Use a new follow-up task instead of reopening `TASK-297`,
  because the legacy refactor is already merged and the remediation is
  materially new work.
- 2026-03-11: After `TASK-300`, freeze the routed legacy `v1` task CLI
  surfaces so `TASK-299` does not reopen the compatibility-preserving
  packaging move.
- 2026-03-11: After introducing the versioned shell, implement new task
  workflow behavior only under `src/horadus_cli/v2/` rather than beside
  unversioned legacy modules.
- 2026-03-11: Apply the 300-line cap only to new `v2` Python files created for
  this task; frozen legacy files are exempt.
- 2026-03-11: Use a temporary public `tasks-v2` command family as the parity
  and rollout seam, then remove it before task closure so `horadus tasks ...`
  remains the only public workflow surface afterward.
- 2026-03-11: Preserve the currently shipped `finish` recovery behavior during
  the cutover; the scenarios captured by `TASK-289` and `TASK-291` are already
  part of the canonical baseline rather than new scope for this task.

## Risks / Foot-guns

- the `v2` cutover can drift from current `horadus tasks` behavior -> add
  explicit parity tests against representative pre-cutover scenarios
- a new hidden monolith can reappear in `v2` -> fail the task if any new `v2`
  Python file exceeds 300 lines
- the implementation can silently depend on legacy internals -> keep `v2`
  modules self-owned and block direct dependence on a new compatibility core
- app-level routing can accidentally alter legacy behavior -> keep the public
  `tasks` surface stable, validate `tasks` vs `tasks-v2` before the cutover,
  and limit the final change to the `v1` -> `v2` implementation switch
- the repo can accidentally leave `tasks-v2` behind as a permanent second
  surface -> require parser/tests/docs to prove `tasks-v2` is removed before
  task closure

## Validation Commands

- `uv run --no-sync pytest tests/unit -q -k "task_workflow_v2 or horadus_cli"`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `src/horadus_cli/app.py`
  - new `src/horadus_cli/v2/`
  - new `tests/unit/*v2*.py`
