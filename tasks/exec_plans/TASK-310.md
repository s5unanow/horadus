# TASK-310: Remove Duplicated App Runtime Modules from `src/horadus_cli/v2/runtime`

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: Done
- Planning Gates: Required — package-boundary cleanup across CLI, app/runtime modules, tests, and coverage config

## Goal (1-3 lines)

Remove the duplicated runtime mirror under `src/horadus_cli/v2/runtime/` and
route shipped CLI/runtime-backed command surfaces to the canonical neutral app
packages under `src/core/`, `src/eval/`, `src/processing/`, and `src/storage/`.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-310`)
  - `TASK-300`, `TASK-301`, `TASK-303`
  - `AGENTS.md` ownership and workflow guidance
- Runtime/code touchpoints:
  - `src/horadus_cli/v2/runtime/`
  - `src/horadus_cli/v2/ops_commands.py`
  - `src/cli.py`
  - `src/core/`
  - `src/eval/`
  - `src/processing/`
  - `src/storage/`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/horadus_cli/v2/test_ops_commands.py`
  - `pyproject.toml`
  - `docs/ARCHITECTURE.md`
- Preconditions/dependencies:
  - preserve shipped `horadus` CLI behavior
  - preserve current command names, output contracts, and runtime-backed CLI features
  - do not move repo-workflow tooling back out of `tools/horadus/`
  - do not introduce a new duplicate app-runtime ownership surface under `src/horadus_cli/`
  - reconcile any behavior that exists only in the duplicate tree before deleting it
  - remove the existing coverage omit for `src/horadus_cli/v2/runtime/` as part of the cleanup

## Outputs

- Expected behavior/artifacts:
  - `src/horadus_cli/v2/runtime/` removed completely
  - `src/horadus_cli/v2/ops_commands.py` and `src/cli.py` import canonical owners from neutral runtime packages
  - tests updated to import the canonical runtime owners rather than the CLI mirror
  - architecture/import checks that fail if non-test code reintroduces `src.horadus_cli.v2.runtime` imports
  - coverage configuration no longer carries explicit `v2/runtime` omissions
  - docs updated to describe `src/horadus_cli/` as CLI adapter/routing code only
- Validation evidence:
  - search results showing no non-test imports from `src.horadus_cli.v2.runtime`
  - CLI regression tests for runtime-backed command paths still green
  - targeted runtime tests green against canonical module owners
  - mypy and unit-coverage gate green after the removal

## Non-Goals

- Explicitly excluded work:
  - changing user-facing CLI behavior or command names
  - moving repo workflow/tooling out of `tools/horadus/`
  - broad app-runtime refactors unrelated to deleting the duplicate namespace
  - redesigning runtime package taxonomy beyond restoring canonical ownership

## Scope

- In scope:
  - inventory every production and test caller of `src.horadus_cli.v2.runtime`
  - map each duplicated runtime module to its canonical owner under `src/`
  - rewire CLI and tests to canonical runtime modules
  - reconcile behavior deltas discovered between canonical and duplicate copies
  - remove the duplicate runtime tree
  - remove stale configuration/docs references to the duplicate tree
  - add regression guards against reintroduction
- Out of scope:
  - feature work inside calibration/eval/processing/storage unrelated to parity reconciliation
  - CLI parser or output redesign
  - speculative package moves outside the canonical neutral runtime homes

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - rewire shipped CLI callers directly to canonical `src/core`, `src/eval`, `src/processing`, and `src/storage` owners, then delete the duplicate tree
- Rejected simpler alternative:
  - keeping `src/horadus_cli/v2/runtime/` as a permanent mirror preserves a second ownership tree and ongoing drift risk
- First integration proof:
  - runtime-backed `horadus` command paths pass using only canonical `src/*` runtime modules with the duplicate namespace removed
- Waivers:
  - temporary compatibility shims are allowed only if they are strictly transitional inside the task branch and removed before task closure

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory every caller of `src.horadus_cli.v2.runtime`, including:
     - `src/cli.py`
     - `src/horadus_cli/v2/ops_commands.py`
     - `tests/horadus_cli/v2/test_cli.py`
     - `tests/horadus_cli/v2/test_ops_commands.py`
     - `pyproject.toml` coverage omit entries
   - inventory the full module map from duplicate owners to canonical owners:
     - `runtime/core/*` -> `src/core/*`
     - `runtime/eval/*` -> `src/eval/*`
     - `runtime/processing/*` -> `src/processing/*`
     - `runtime/storage/*` -> `src/storage/*`
   - classify duplicates into:
     - namespace-only copies
     - behavior deltas requiring reconciliation
   - confirm which command families actually depend on runtime-backed modules today, especially `ops`

2. Implement
   - rewire `src/cli.py` to import canonical config/settings from `src/core/config.py`
   - rewire `src/horadus_cli/v2/ops_commands.py` to import canonical runtime owners from neutral `src/*` packages
   - rewire CLI tests to target canonical runtime owners instead of the duplicate CLI namespace
   - reconcile behavior deltas before removal, with explicit focus on:
     - `src/core/observability.py` vs duplicate metrics-registry behavior
     - any other non-import-only diffs that remain after namespace normalization
   - remove `src/horadus_cli/v2/runtime/`
   - remove coverage omit entries for the deleted tree from `pyproject.toml`
   - update docs to describe `src/horadus_cli/` as adapter/routing code only
   - add regression guards that fail on new non-test imports from `src.horadus_cli.v2.runtime`

3. Validate
   - run targeted import searches proving production code no longer references the deleted namespace
   - run CLI regression coverage for runtime-backed paths
   - run targeted tests against canonical runtime owners
   - run mypy for `src/`
   - run unit tests with coverage and confirm the deleted-tree omit is gone cleanly

4. Ship (PR, checks, merge, main sync)
   - update task/docs surfaces required by repo policy
   - run required local gates
   - open PR, complete review/check flow, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-12: Treat `src/horadus_cli/v2/runtime/` as migration scaffolding, not a permanent ownership boundary.
- 2026-03-12: Restore canonical ownership to neutral app/runtime packages under `src/` rather than moving app/runtime logic deeper into the CLI namespace.
- 2026-03-12: Use direct rewiring to canonical owners as the preferred cleanup path; compatibility shims are acceptable only as short-lived in-branch transition aids.
- 2026-03-12: Reconcile substantive behavior deltas in canonical owners before deleting duplicate copies, rather than deleting first and discovering regressions later.

## Risks / Foot-guns

- the duplicate tree may contain one-off behavioral fixes not present in canonical owners -> diff and reconcile before deletion, with explicit tests
- CLI tests may accidentally continue validating only import wiring instead of behavior -> keep behavior-focused assertions on runtime-backed command paths
- deleting the duplicate tree can expose hidden coverage or import assumptions -> remove coverage carveouts and add import-boundary checks in the same change
- app/runtime modules can drift again through copy-paste reintroduction -> add a regression guard that forbids non-test imports from the removed namespace

## Validation Commands

- `rg -n "horadus_cli\\.v2\\.runtime|src/horadus_cli/v2/runtime" src tests docs pyproject.toml .github Makefile -S`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_cli.py tests/horadus_cli/v2/test_ops_commands.py -q`
- `uv run --no-sync pytest tests/unit -q -k "calibration or observability or benchmark or dry_run_pipeline or llm_policy"`
- `uv run --no-sync mypy src/`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `src/cli.py`
  - `src/horadus_cli/v2/ops_commands.py`
  - `src/core/`
  - `src/eval/`
  - `src/processing/`
  - `src/storage/`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/horadus_cli/v2/test_ops_commands.py`
  - `pyproject.toml`
- Observed inventory:
  - duplicate runtime modules: 33
  - namespace-only duplicates after import-path normalization: 27
  - modules needing explicit parity review before deletion: 6
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
