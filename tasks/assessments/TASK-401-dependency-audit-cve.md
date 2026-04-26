# TASK-401 Dependency Audit CVE Resolution

Review date: 2026-04-27

## Scope

- Resolved the dependency-audit blocker reported by TASK-400 PR #371.
- Updated the frozen dev dependency set from `pip==26.0.1` to `pip==26.1`.
- Left `pyproject.toml` and the dependency-audit allowlist unchanged because the
  existing `pip-audit` dependency can resolve to the fixed transitive `pip`
  version without a policy exception.

## Validation Notes

- `./scripts/run_dependency_audit.sh` passes locally after the lockfile update.
- `uv lock --check` passes after the lockfile update.
- Integration proof: N/A. This task only changes the development dependency
  lockfile and task ledgers; it does not touch runtime or integration-covered
  paths.
- Docs update: N/A. No user-facing behavior, workflow contract, or operator
  command changed.

## Workflow Notes

- `TASK-400` existed only on open PR #371 when this blocker was discovered, so
  `main` still advertised `TASK-400` as the next available ID.
- Reserved the in-flight `TASK-400` ID on `main` before using the normal intake
  promotion flow, producing `TASK-401` for this blocker task.
- Started `TASK-401` with `ALLOW_OPEN_TASK_PRS=1` because the open PR was the
  blocked task this security fix was created to unblock.

## Source Notes

- Local blocker: `./scripts/run_dependency_audit.sh` reported
  `pip 26.0.1 CVE-2026-3219`.
- Public CVE summaries identify `pip < 26.1` / `pip <= 26.0.1` as affected,
  making a lockfile update to `pip==26.1` the narrow remediation.
