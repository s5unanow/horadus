# TASK-257: Fail Pre-Commit and CI When Coverage Drops Below 100%

## Status

- Owner: Codex
- Started: 2026-03-09
- Current state: Completed

## Goal (1-3 lines)

Make 100% measured coverage a hard repo policy instead of a documented target.
Align the canonical local coverage path, pre-commit, and CI so they all fail
closed when runtime coverage drops below 100%.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-257`)
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `src/horadus_cli/task_commands.py`
  - `tests/horadus_cli/v1/test_cli.py`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `.pre-commit-config.yaml`
  - `docs/AGENT_RUNBOOK.md`
  - `README.md`
- Preconditions/dependencies:
  - `TASK-253` already merged and repo coverage currently reaches 100%
  - Canonical workflow should keep `horadus tasks local-gate --full` as the
    post-task validation authority

## Outputs

- Expected behavior/artifacts:
  - Hard `--cov-fail-under=100` enforcement on the canonical local coverage run
  - Matching enforcement in pre-commit and CI
  - Updated docs describing when the coverage gate runs and how to debug it
  - Regression tests covering command wiring/drift
- Validation evidence:
  - Targeted unit tests for CLI gate step definitions
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - Re-raising repo coverage back to 100% if an unrelated regression appears
  - Broad restructuring of the full local gate beyond the coverage threshold
  - Closing stale sprint ledger entries for already-merged tasks outside
    `TASK-257`

## Scope

- In scope:
  - Coverage threshold enforcement wiring
  - Documentation alignment for coverage enforcement
  - Tests for local-gate command wiring and guard drift
- Out of scope:
  - New coverage-producing tests unrelated to enforcement
  - Workflow changes outside coverage gate surfaces

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-09: Execute `TASK-257` first because `TASK-253` already established
  100% coverage, while pre-commit and CI still do not enforce it.
- 2026-03-09: Centralize the unit coverage invocation in one repo-owned script
  so the CLI full gate, pre-push hook, and CI share the same hard-fail
  threshold and reporting flags.
- 2026-03-09: Treat the current `97.86%` unit coverage result as a real
  prerequisite blocker for `TASK-257`, not something to hide with a weaker
  threshold or a narrower command.

## Risks / Foot-guns

- Coverage enforcement can fail if local/CI command lines diverge ->
  centralize expected command shape in CLI step tests and keep docs aligned.
- Adding coverage to pre-commit can be expensive -> scope it to `pre-push`
  rather than the inner-loop `pre-commit` hook unless current policy already
  requires otherwise.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v1/test_cli.py -k "local_gate or coverage" -q`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none; backlog entry is authoritative
- Relevant modules:
  - `src/horadus_cli/task_commands.py`
  - `tests/horadus_cli/v1/test_cli.py`
- Validation evidence:
  - Task-scoped regression tests passed: `248 passed`
  - Canonical full local gate passed end to end, including the hard
    `pytest-unit-cov` step at `100%`
  - The remaining live coverage regressions were closed with behavior-focused
    tests in `tests/horadus_cli/v1/test_cli.py`,
    `tests/unit/eval/test_artifact_provenance.py`, and
    `tests/unit/processing/test_tier2_classifier_additional.py`
