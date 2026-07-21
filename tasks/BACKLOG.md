# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-418`.
- Checklist boxes in this file are planning snapshots; canonical completion status lives in `tasks/CURRENT_SPRINT.md` and `tasks/COMPLETED.md`.

## Task Labels

- `[REQUIRES_HUMAN]`: task includes a mandatory manual step and must not be auto-completed by an agent.
- For `[REQUIRES_HUMAN]` tasks, agents may prepare instructions/checklists only and must stop for human completion.

## Task Spec Contract

- New implementation specs should state: problem statement, inputs, outputs, non-goals, and acceptance criteria.
- Canonical lightweight spec template: `tasks/specs/TEMPLATE.md`
- Use the template as a default shape, then keep individual specs only as detailed as the task complexity requires.

## Task Branching Policy (Hard Rule)

- Treat `AGENTS.md` as the canonical workflow-policy owner; keep this ledger focused on open task definitions.
- Every implementation task must run on a dedicated task branch created from `main`, with one `TASK-XXX` per branch/PR.
- Start task work with the canonical guarded flow:
  - `uv run --no-sync horadus tasks preflight`
  - `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
- `make task-preflight`, `make task-start`, and `make agent-safe-start` remain compatibility wrappers only.
- Every task PR body must include exactly one canonical metadata line: `Primary-Task: TASK-XXX`.
- Do not claim a task is complete, done, or finished until `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` passes or `horadus tasks finish TASK-XXX` completes successfully.
- Keep backlog entries concise and task-shaped; detailed implementation boundaries, migration strategy, risks, and validation belong in the exec plan when one exists.

---

## Open Task Ledger

---

### TASK-417: Clear full local-gate blockers surfaced by TASK-416
**Priority**: P0
**Estimate**: XS

Clear the repository-wide blockers surfaced by the `TASK-416` full local gate:
the stale deployment guide verification marker and the current dependency
audit findings for `click` and `lxml-html-clean`.

**Assessment-Ref**:
- TASK-416 local-gate blocker 2026-07-21
- INTAKE-0074 re-audit 2026-07-21

**Files**: `docs/DEPLOYMENT.md`, `pyproject.toml`, `uv.lock`

**Acceptance Criteria**:
- [x] Review docs/DEPLOYMENT.md against current deployment configuration and update stale content as needed.
- [x] Update the Last Verified marker only after verification.
- [x] Resolve `click` to at least 8.3.3 and `lxml-html-clean` to at least 0.4.5 without vulnerability allowlist exceptions.
- [x] The docs-freshness check and canonical full local gate pass.

**Implementation Notes**:
- Verified the documented compose services, images, profiles, networks, ingress headers, health endpoints, Make targets, environment variables, and referenced runbooks against current repo truth.
- Targeted tests: N/A — dependency metadata and docs/ledger-only changes with no executable code change.
- Integration proof: N/A — no integration-covered runtime path changed.
- Canonical proof: all 17 full local-gate steps passed, including dependency audit and Docker-backed integration.

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
