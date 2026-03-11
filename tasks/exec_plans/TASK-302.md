# TASK-302: Isolate Horadus CLI Tests Into a Self-Contained Suite

## Status

- Owner: Codex
- Started: 2026-03-11
- Current state: In progress

## Goal (1-3 lines)

Move the Horadus CLI tests into a dedicated `tests/horadus_cli/` suite so the
CLI package can evolve behind a self-contained regression surface instead of
sharing the app-wide `tests/unit/` root.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-302`)
- Runtime/code touchpoints:
  - `tests/horadus_cli/`
  - `tests/unit/scripts/`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `scripts/run_unit_coverage_gate.sh`
- Preconditions/dependencies:
  - preserve current CLI coverage and behavior checks
  - keep CLI tests in the canonical local and CI validation paths after the move

## Outputs

- Expected behavior/artifacts:
  - dedicated `tests/horadus_cli/` suite with package-scoped CLI tests
  - local fixture wiring that lives with the CLI tests
  - local and CI runners updated to include the isolated CLI suite
- Validation evidence:
  - focused CLI suite passes from its new location
  - unit coverage gate still passes with the new tree included
  - pre-commit and pre-push succeed before the PR is opened

## Non-Goals

- Explicitly excluded work:
  - implementing `v2` runtime behavior
  - splitting the `v1` CLI monolith into many smaller test files
  - moving non-CLI repo-script tests out of `tests/unit/scripts/` unless they
    are required for the CLI package move
  - reorganizing unrelated app-domain unit tests

## Scope

- In scope:
  - create a dedicated `tests/horadus_cli/` tree
  - move CLI-focused tests and shared fixtures into that tree
  - keep shell/router tests close to the CLI package boundary
  - update runner commands and coverage gates to include the new tree
  - update live task/docs references that would otherwise point to deleted test paths
- Out of scope:
  - deeper runtime refactors in `src/horadus_cli/`
  - moving broad non-CLI test domains

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory current CLI-focused tests and fixture dependencies
   - identify runner commands that still assume `tests/unit/` is the whole unit suite
2. Implement
   - move CLI tests into `tests/horadus_cli/`
   - add package-local fixture wiring for the CLI suite
   - update references and runner commands to the new paths
3. Validate
   - run focused CLI tests from the new tree
   - run local pre-commit and pre-push gates
4. Ship (PR, checks, merge, main sync)
   - push the task branch
   - open a PR for manual review

## Decisions (Timestamped)

- 2026-03-11: Keep the isolated CLI suite under `tests/` rather than moving tests into `src/horadus_cli/`, so runtime code stays shipping-only.
- 2026-03-11: Allow `v1` CLI tests to remain monolithic inside the dedicated CLI suite for now; isolation is more important than immediate test-file decomposition.
- 2026-03-11: Leave non-CLI script tests under `tests/unit/scripts/` unless they are primarily package-scoped CLI coverage.

## Risks / Foot-guns

- runner drift can silently drop CLI coverage -> update local and CI test commands in the same task
- path moves can leave stale docs/spec commands behind -> patch live references that point at deleted files
- fixture/plugin imports can break after relocation -> keep package-local `conftest.py` wiring in the new CLI tree

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/ -q`
- `uv run --no-sync pytest tests/unit/scripts/test_task_context_pack.py tests/unit/scripts/test_check_agent_task_eligibility.py -q`
- `./scripts/run_unit_coverage_gate.sh`
- `uv run --no-sync pre-commit run --all-files`
- `uv run --no-sync pre-commit run --hook-stage pre-push --all-files`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `tests/horadus_cli/`
  - `tests/unit/scripts/`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `scripts/run_unit_coverage_gate.sh`
