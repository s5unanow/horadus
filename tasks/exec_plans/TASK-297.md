# TASK-297: Split `task_commands.py` Into Focused Workflow Modules

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: In progress

## Goal (1-3 lines)

Refactor `src/horadus_cli/task_commands.py` into smaller internal modules with
clear responsibility boundaries so future task-workflow changes are easier to
reason about, test, and review without changing the public `horadus tasks ...`
CLI surface.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-297`)
- Runtime/code touchpoints: `src/horadus_cli/task_commands.py`, `src/horadus_cli/task_repo.py`, `tests/unit/test_cli.py`, `tests/unit/scripts/`, `docs/AGENT_RUNBOOK.md`, `README.md`, `AGENTS.md`
- Preconditions/dependencies:
  - `TASK-294` and `TASK-295` already landed archive-aware closure and stricter finish/lifecycle invariants
  - `TASK-296` added more start/preflight intake logic, increasing the value of isolating workflow concerns before future changes pile into the same file

## Outputs

- Expected behavior/artifacts:
  - new internal modules separating process helpers, preflight/start logic, ledger/archive mutation, finish/review-gate orchestration, and lifecycle verification
  - explicit homes for workflow friction/reporting helpers and shared cross-cutting dataclasses/config/result models
  - explicit owner for cross-domain command composition so orchestration does not drift back into `task_commands.py`
  - `src/horadus_cli/task_commands.py` reduced to a thin CLI facade with handler wiring and parser registration
  - preserved CLI behavior for all existing `horadus tasks ...` commands, including command names, supported options, exit codes, and operator-facing output/error shapes unless a separately scoped behavior change is explicitly documented
  - `tasks/exec_plans/TASK-297-compatibility.md` maintained as the checked-in source of truth for:
    - command compatibility inventory
    - command-to-scenario coverage mapping
    - caller/import inventory for extracted symbol groups
    - fallback-sensitive baseline scenarios
    - dependency/ownership map for extracted modules
- Validation evidence:
  - populated compatibility artifact captured before the first extraction commit
  - focused unit coverage across extracted modules and unchanged CLI behavior
  - unaffected workflow regression coverage for preflight/start, finish/lifecycle, and archive-aware task lookup
  - full local gate before merge

## Non-Goals

- Explicitly excluded work:
  - changing task file formats, archive layout, or review-timeout policy
  - redesigning task workflow UX or renaming commands/options
  - opportunistic policy changes hidden inside the refactor
  - moving unrelated Horadus CLI surfaces that do not belong to task workflow code

## Scope

- In scope:
  - extraction of internal helpers from `task_commands.py`
  - explicit module ownership for start/preflight, close-ledgers/archive, finish/review gate, lifecycle verification, and subprocess helper code
  - explicit owner for cross-domain command composition and workflow policy coordination
  - explicit ownership boundaries between orchestration modules and `task_repo.py`
  - import-boundary cleanup to avoid cycles and duplicated helper logic
  - module-level and CLI-level regression tests proving behavior preservation
- Out of scope:
  - new workflow features unless they are strictly required to preserve existing behavior during extraction
  - broad `task_repo.py` redesign outside interfaces required by the split
  - documentation rewrites beyond ownership/contributor guidance updates

## Plan (Keep Updated)

1. Create and populate `tasks/exec_plans/TASK-297-compatibility.md` with:
   - command/subcommand/flag inventory
   - current symbol-group to planned-module map
   - caller/import inventory tied back to command rows
   - fallback-sensitive baseline scenarios
   - allowed dependency graph and ownership map
   - explicit scenario coverage links for every command row before any code move
2. Define target module boundaries, shared types/helpers, and explicit compatibility checklist
3. Capture baseline observable CLI behavior for touched command families before moving code and freeze the populated artifact as the review baseline
4. Extract low-risk helpers first (`task_process`, pure utility helpers) and run phase validation
5. Extract friction/reporting helpers and shared cross-cutting types into named homes before splitting higher-level workflow domains
6. Extract workflow domains incrementally:
   - task-query read paths
   - preflight/start
   - ledgers/archive
   - finish/review gate
   - lifecycle/strict verification
7. Introduce the explicit cross-domain orchestration owner (`task_workflow.py` or equivalent) before any flow needs to compose multiple extracted domains
8. After each extraction phase, run targeted compatibility checks against the checked-in baseline before proceeding
   - no phase is complete until every touched command row still has at least one validating scenario run or an explicit unchanged-by-construction rationale recorded in the compatibility artifact
9. Reduce `task_commands.py` to a facade and keep parser/handler compatibility
10. Rebalance tests toward extracted modules while retaining end-to-end CLI regression coverage
11. Validate full workflow behavior against the baseline scenario inventory and compatibility matrix, then ship

## Decisions (Timestamped)

- 2026-03-10: Keep the public CLI surface stable and treat this as an internal-structure refactor, because the repo needs lower maintenance cost without forcing workflow retraining.
- 2026-03-10: Prefer incremental extraction commits over a single mechanical move so each responsibility seam can be reviewed with behavior-preserving tests.
- 2026-03-10: Treat text compatibility as contract compatibility, not byte-for-byte stability; preserve command names/options, JSON fields, exit codes, stream routing, blocker classes, and recovery guidance while allowing harmless formatting drift.
- 2026-03-10: Use a dedicated cross-domain orchestration module (`task_workflow.py` or an explicitly named equivalent) so command composition does not remain in `task_commands.py` and does not leak into `task_shared.py` or `task_repo.py`.

## Risks / Foot-guns

- Hidden behavior drift during helper moves -> require regression coverage for unaffected command paths after each extraction phase
- Cyclic imports between new modules -> define ownership up front for shared dataclasses, process helpers, and task-repo integration points
- Turning the refactor into a stealth feature task -> keep non-goals explicit and isolate any required bug fix with dedicated tests and commit notes
- Over-fragmenting into many tiny modules -> split by workflow domain, not by arbitrary function count
- Test churn obscuring real regressions -> preserve a small layer of CLI-level end-to-end tests while moving implementation-detail tests closer to extracted modules
- A "thin facade" can stay artificially fat if not bounded -> explicitly track which responsibilities are allowed to remain in `task_commands.py` and reject convenience leakage during review
- Friction/fallback regressions can be missed if only happy paths are re-tested -> capture baseline fallback-sensitive scenarios before extraction and compare them again before merge
- `task_shared.py` can become a new dumping ground -> allow only types/exceptions/config shared by 2+ workflow domains and reject workflow logic or repo access in that module
- `task_repo.py` can accidentally absorb orchestration helpers during the split -> keep it read-side only and push write/orchestration logic into dedicated workflow modules
- The compatibility artifact can drift into a checklist-without-proof -> require concrete rows for every command family, symbol group, caller/import edge, and fallback-sensitive scenario before extraction begins and update it as each phase lands

## Validation Commands

- Phase validation after each extraction step:
  - targeted unit tests for the moved domain
  - at least one unaffected CLI regression path from another domain
  - import / command-startup smoke check for the touched command family
  - observable CLI checks for touched flows, including `--help`, parser failures, stdout/stderr routing, and representative exit-code paths where applicable
  - update `tasks/exec_plans/TASK-297-compatibility.md` with any newly discovered indirect command/caller impact before proceeding
  - mark touched command rows with the validating scenario ids or explicit unchanged-by-construction rationale used for that phase
- `uv run --no-sync pytest tests/unit/test_cli.py -q`
- `uv run --no-sync pytest tests/unit/scripts/ -q`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules:
  - `src/horadus_cli/task_commands.py`
  - `src/horadus_cli/task_repo.py`
  - `tests/unit/test_cli.py`
  - `tests/unit/scripts/`
