# TASK-312: Split `tests/horadus_cli/v2/test_cli.py` into Focused Ownership-Aligned Modules

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: Done
- Planning Gates: Required — the test split will touch many files and must preserve shared CLI/workflow coverage without creating new overlap

## Goal (1-3 lines)

Break the monolithic `tests/horadus_cli/v2/test_cli.py` suite into smaller,
ownership-aligned test modules that are easier to navigate, maintain, and
extend. Preserve current behavior coverage while reducing fixture bleed and
mixed-domain coupling.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-312`)
  - `AGENTS.md` repo workflow and test-maintainability constraints
- Runtime/code touchpoints:
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/horadus_cli/v2/test_ops_commands.py`
  - `tests/horadus_cli/v2/task_repo_fixtures.py`
  - `tools/horadus/python/horadus_cli/app.py`
  - `tools/horadus/python/horadus_cli/result.py`
  - `tools/horadus/python/horadus_cli/task_commands.py`
  - `tools/horadus/python/horadus_cli/task_query.py`
  - `tools/horadus/python/horadus_cli/task_preflight.py`
  - `tools/horadus/python/horadus_cli/task_friction.py`
  - `tools/horadus/python/horadus_cli/task_workflow.py`
  - `tools/horadus/python/horadus_cli/task_lifecycle.py`
  - `tools/horadus/python/horadus_cli/task_finish.py`
  - `tools/horadus/python/horadus_cli/task_ledgers.py`
  - `tools/horadus/python/horadus_cli/triage_commands.py`
- Preconditions/dependencies:
  - Keep test semantics and command behavior coverage unchanged
  - Avoid broad autouse fixtures that affect unrelated modules
  - Preserve the existing `pytest_plugins`-backed synthetic task repo support
  - Keep the split aligned with production ownership boundaries, not arbitrary file-size thresholds

## Outputs

- Expected behavior/artifacts:
  - focused test files under `tests/horadus_cli/v2/` grouped by production owner or tightly related workflow area
  - shared helper placement that makes cross-cutting seams explicit
  - a finish-focused sub-area or equivalent scoping strategy for review-gate-heavy tests
  - removal of the monolithic `test_cli.py` file once its coverage has been redistributed
- Validation evidence:
  - targeted pytest runs for the split CLI test surface
  - at least one full `tests/horadus_cli` run confirming no collection/import regressions

## Non-Goals

- Explicitly excluded work:
  - changing CLI command behavior or output contracts
  - rewriting workflow internals just to simplify tests
  - broad renames or module moves in production code unless a tiny import/test seam adjustment is required

## Scope

- In scope:
  - map the existing monolith into stable ownership-aligned test modules
  - extract neutral helpers into `conftest.py` or a small helper module only when reuse is real
  - keep finish/review-gate defaults local to the finish-oriented tests
  - preserve or improve test discoverability with clear file names
- Out of scope:
  - adding new CLI features
  - changing unrelated test suites outside `tests/horadus_cli/v2/`
  - introducing a second monolith via an oversized helper or fixture module

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - split by current production module ownership and workflow area, with only a thin shared helper layer
- Rejected simpler alternative:
  - keeping one giant file with comment banners would preserve the current navigation and fixture-isolation problems
- First integration proof:
  - `uv run --no-sync pytest tests/horadus_cli/v2 -q`
- Waivers:
  - exact file names may adjust during implementation if a boundary becomes clearer after helper extraction

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory `test_cli.py` into ownership-aligned clusters
   - identify helpers that are truly cross-cutting versus domain-specific
   - choose the final test file map before moving code
2. Implement
   - create the new test modules and move tests cluster by cluster
   - extract only neutral helpers/fixtures into shared support files
   - keep finish/review-gate fixtures scoped to the finish test surface
   - delete the old monolith after coverage is fully redistributed
3. Validate
   - run targeted pytest commands for each moved area
   - run a broader `tests/horadus_cli` collection/regression check
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Use ownership-aligned test modules instead of `test_cli_part_N.py` slices so maintainers can find the right test surface without opening multiple arbitrary files.
- 2026-03-13: Keep finish/review-gate monkeypatch defaults local to finish tests because those defaults would create hidden coupling if promoted to package-wide autouse fixtures.
- 2026-03-13: Register `tests.horadus_cli.v2.task_repo_fixtures` from top-level `tests/conftest.py` instead of `tests/horadus_cli/v2/conftest.py` so the split still collects cleanly under broader `tests/horadus_cli` and unit-suite runs.

## Risks / Foot-guns

- Shared fixtures move too high and create hidden cross-module coupling
  -> keep only neutral helpers global and keep behavioral monkeypatching local.
- Imports or helper names drift during moves and silently drop coverage
  -> move tests in small clusters and run targeted pytest after each cluster.
- Production ownership boundaries are mirrored inconsistently in test names
  -> lock the destination file map before code movement and keep names source-owner-oriented.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2 -q`
- `uv run --no-sync pytest tests/horadus_cli -q`
- `make agent-check`

## Notes / Links

- Spec:
  - none; backlog entry plus exec plan are sufficient for this task
- Relevant modules:
  - `tests/horadus_cli/v2/test_cli.py`
  - `tools/horadus/python/horadus_cli/task_finish.py`
  - `tools/horadus/python/horadus_cli/task_preflight.py`
  - `tools/horadus/python/horadus_cli/task_query.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
