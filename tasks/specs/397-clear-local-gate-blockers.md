---
task_id: TASK-397
retrieval:
  kind: task-spec
  status: active
  canonical: true
  supersedes: []
  superseded_by: null
---

# TASK-397: Clear local-gate blockers surfaced by TASK-387

## Problem Statement

`TASK-387` uncovered repo-wide blockers outside its scope: stale docs freshness
metadata, missing planning artifacts for active hotspot tasks, and a dependency
audit failure on `lxml`. Those blockers need to move onto their own task so the
original branch can stay single-task and policy-compliant.

## Inputs

- `tasks/BACKLOG.md` and `tasks/CURRENT_SPRINT.md` for live task scope
- `docs/ENVIRONMENT.md` for the stale freshness marker
- `tasks/exec_plans/TASK-389.md`, `tasks/exec_plans/TASK-390.md`,
  `tasks/exec_plans/TASK-392.md` for the missing authoritative planning
  artifacts
- `pyproject.toml` and `uv.lock` for the `lxml` dependency posture

## Outputs

- Fresh docs marker in `docs/ENVIRONMENT.md`
- Authoritative exec plans for the currently blocking hotspot tasks
- Repo dependency posture updated so dependency audit no longer fails on
  `lxml`
- Validation evidence for docs freshness, dependency audit, targeted workflow
  tests, `make agent-check`, and `horadus tasks local-gate --full`

## Non-Goals

- Finishing `TASK-387` on this branch
- Implementing `TASK-389`, `TASK-390`, or `TASK-392` beyond seeding their
  planning artifacts
- Push/PR workflow behavior changes

**Planning Gates**: `Not Required` — this is blocker cleanup across docs,
planning artifacts, and dependency metadata without shared runtime or workflow
behavior changes.

## Acceptance Criteria

- [ ] Docs freshness no longer fails because `docs/ENVIRONMENT.md` is stale or
      because active hotspot tasks `TASK-389`/`TASK-390`/`TASK-392` lack
      authoritative planning artifacts when `tasks/BACKLOG.md` is touched.
- [ ] Dependency audit passes after updating the repo-owned `lxml` dependency
      posture to remediate `CVE-2026-41066`.

## Validation

- `uv run --no-sync python scripts/check_docs_freshness.py`
- `./scripts/run_dependency_audit.sh`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

Integration proof: N/A — the task does not touch integration-covered runtime or
push/PR workflow surfaces.
