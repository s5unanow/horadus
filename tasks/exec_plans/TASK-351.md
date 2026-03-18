# TASK-351: Bring `scripts/` under the main lint, type, security, and coverage posture

## Status

- Owner: Codex
- Started: 2026-03-18
- Current state: In progress
- Planning Gates: Required — shared workflow/config gate expansion across repo-owned Python surfaces

## Goal (1-3 lines)

Expand the canonical repo-owned lint, typecheck, security, and measured-coverage
paths so tracked Python under `scripts/` is enforced alongside `src/` and
`tools/`. Keep the change fail-closed and parity-tested across local, CLI, and
CI gate surfaces.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-351`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `scripts/`, `Makefile`, `.github/workflows/ci.yml`, `pyproject.toml`, `.pre-commit-config.yaml`, `scripts/run_unit_coverage_gate.sh`, `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`, `tests/horadus_cli/v2/test_task_workflow.py`, `tests/unit/scripts/`, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies:
  - `uv`-managed dev tooling for `ruff`, `mypy`, `pytest`, and `bandit`
  - existing canonical local-gate parity tests
  - shared workflow callers that currently hard-code `src/` and `tools/` only:
    - `Makefile`: `format`, `lint`, `typecheck`, `agent-check`, `security`, `ci`
    - `.github/workflows/ci.yml`: lint, typecheck, unit-test, and security jobs
    - `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`: `full_local_gate_steps()`
    - `scripts/run_unit_coverage_gate.sh`: canonical measured coverage command
    - `tests/horadus_cli/v2/test_task_workflow.py`: gate-parity assertions

## Outputs

- Expected behavior/artifacts:
  - canonical lint/type/security commands include tracked Python under `scripts/`
  - canonical measured coverage includes `scripts/` unless a path-specific omission is justified
  - local-gate/CI/Makefile parity remains explicit and regression-tested
  - runbook guidance reflects the expanded repo-owned Python scope
- Validation evidence:
  - updated gate-parity and script-focused tests
  - direct `ruff`/`mypy`/`bandit`/coverage validation on the changed scope
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - broad refactors of unrelated scripts beyond what the stricter gates require
  - blanket exclusions for all of `scripts/`
  - changing non-Python workflow surfaces unless required for gate parity

## Scope

- In scope:
  - repo-owned gate command expansions for `scripts/`
  - narrow false-positive handling where specific scripts need justified treatment
  - parity tests and docs for the expanded gate surface
- Out of scope:
  - new analyzer families beyond lint, typecheck, security, and measured coverage
  - unrelated backlog or sprint reshaping beyond task-close updates and the already-open `TASK-354` backlog addition

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - update the existing canonical commands and helpers in place so all entry points share one widened contract
- Rejected simpler alternative:
  - leaving `scripts/` outside the main posture or adding a blanket carve-out for all scripts
- First integration proof:
  - `tests/horadus_cli/v2/test_task_workflow.py` proves the CLI local-gate steps still match the widened Makefile/CI contract
- Waivers:
  - None planned; any script-specific exclusion must be path-specific, justified, and tested

## Plan (Keep Updated)

1. Preflight (create exec plan, guarded task start, inspect current failures on `scripts/`)
2. Implement widened lint/type/security/coverage scope plus any narrow script-specific fixes
3. Validate targeted tests, `make agent-check`, local review, and full local gate
4. Ship through PR/review/merge/main-sync using the canonical workflow

## Decisions (Timestamped)

- 2026-03-18: Treat `Makefile`, CI, `task_workflow_lifecycle.py`, and `scripts/run_unit_coverage_gate.sh` as the authoritative shared callers for this task. (They currently encode the repo-owned gate contract that must stay in sync.)
- 2026-03-18: Keep coverage fail-closed and measured for `scripts/` by default, only narrowing with explicit path-level justification if a concrete blocker appears. (Matches the task acceptance criteria and existing hard coverage posture.)

## Risks / Foot-guns

- Existing scripts may fail newly enforced lint/type/security checks -> fix concrete issues or add narrow justified suppressions instead of weakening the whole scope
- Coverage can drop sharply when `scripts/` becomes measured -> add tests for exercised script modules and avoid silent omission drift
- Parity drift across Makefile/CI/local-gate -> update caller assertions in the same task and keep the contract text-based where possible

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_workflow.py -v -m unit`
- `uv run --no-sync pytest tests/unit/scripts/ -v -m unit`
- `make agent-check`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: backlog entry in `tasks/BACKLOG.md`
- Relevant modules: `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`, `scripts/run_unit_coverage_gate.sh`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
