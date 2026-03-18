# TASK-352: Enforce server-side secret and dependency vulnerability scanning in CI

## Status

- Owner: Codex
- Started: 2026-03-18
- Current state: In progress
- Planning Gates: Required — shared CI/security policy change across repo-owned gate surfaces

## Goal (1-3 lines)

Add fail-closed CI enforcement for secrets and dependency vulnerabilities using
repo-owned commands that also participate in the canonical local gate. Keep the
operator path explicit and narrow, with repo-owned baselines or suppressions
only where justified.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-352`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `.github/workflows/ci.yml`, `Makefile`, `.pre-commit-config.yaml`, `pyproject.toml`, `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`, `tests/horadus_cli/v2/test_task_workflow.py`, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies: `uv`-managed dev tooling, existing `.secrets.baseline`, current CI security job, current local-gate parity assertions

## Outputs

- Expected behavior/artifacts:
  - CI runs a repo-owned secret scan against tracked files using `.secrets.baseline`
  - CI runs a real dependency vulnerability audit instead of relying on `uv lock --check`
  - Canonical local gate exposes the same security checks
  - Runbook documents the matching local command path
- Validation evidence:
  - Updated workflow/local-gate parity tests
  - Relevant targeted pytest coverage
  - Direct dry-run/help validation for the selected security tools

## Non-Goals

- Explicitly excluded work:
  - Broad security-policy refactors outside the secret/dependency scan path
  - Reworking unrelated lint/type/coverage scope decisions
  - Clearing future vulnerability suppressions before a concrete finding exists

## Scope

- In scope:
  - Repo-owned secret scan command
  - Repo-owned dependency vulnerability audit command
  - CI/local-gate wiring, docs, and parity tests
- Out of scope:
  - New secret-baseline contents unless the new server-side scan proves they are required
  - Expanding static-analysis scope for `scripts/` beyond what this task needs to run the new checks

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Add explicit repo-owned security commands and call them from both CI and the canonical local gate
- Rejected simpler alternative:
  - Treating `uv lock --check` as a substitute for vulnerability auditing
- First integration proof:
  - Updated local-gate parity tests align with `.github/workflows/ci.yml`
- Waivers:
  - None currently planned

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement repo-owned secret scan and dependency audit commands plus CI/local-gate wiring
3. Validate targeted tests and command behavior
4. Ship checkpoint commit with ledger + implementation changes

## Decisions (Timestamped)

- 2026-03-18: Use `detect-secrets` against tracked files plus `.secrets.baseline` for CI/local parity instead of relying on the pre-commit hook alone. (Keeps the baseline authoritative while moving enforcement server-side.)
- 2026-03-18: Use `pip-audit` as the dependency vulnerability check and keep `uv lock --check` only as lockfile integrity validation. (This adds a real vulnerability feed instead of only syntax/consistency checking.)

## Risks / Foot-guns

- Secret scanning across generated/untracked files could create noisy failures -> scan tracked files only and keep exclusions repo-owned
- Dependency auditing may add network-dependent latency -> pin the tool in dev dependencies and keep the command deterministic against the locked project
- CI/local parity drift -> update the existing parity tests instead of relying on docs alone

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_workflow.py -v -m unit`
- `uv run --no-sync pytest tests/workflow/test_task_workflow.py -v -m unit`
- `uv run --no-sync horadus tasks local-gate --full --dry-run`

## Notes / Links

- Spec: backlog entry in `tasks/BACKLOG.md`
- Relevant modules: `.github/workflows/ci.yml`, `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
