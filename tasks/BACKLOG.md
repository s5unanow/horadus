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

### TASK-416: Update dependency audit CVE blockers
**Priority**: P0
**Estimate**: XS

Refresh the frozen dependency set so the canonical security audit no longer
blocks normal task delivery.
Current reproduced findings: click 8.3.1 PYSEC-2026-2132 and lxml-html-clean
0.4.4 PYSEC-2026-2614.

**Assessment-Ref**:
- INTAKE-0074 re-audit 2026-07-21

**Files**: `pyproject.toml`, `uv.lock`, `scripts/run_dependency_audit.sh`

**Acceptance Criteria**:
- [x] The lockfile resolves click to at least 8.3.3 and lxml-html-clean to at least 0.4.5 without unrelated direct-dependency upgrades.
- [x] ./scripts/run_dependency_audit.sh passes without adding vulnerability allowlist exceptions.
- [x] make secret-scan security dependency-audit and the canonical full local gate pass.

**Implementation Notes**:
- Resolved `click` to 8.4.2 and `lxml-html-clean` to 0.4.5; the related `lxml` patch release moved to 6.1.1.
- Integration proof: N/A — this task changes dependency metadata and the lockfile only, without an integration-covered runtime path.
- Docs update: N/A — the dependency security floor does not change an operator-facing or runtime contract.
- Targeted proof: `make secret-scan security dependency-audit`, the context-pack workflow suite (856 passed), and `make agent-check` passed.
- Delivery note: the dependency metadata landed on `main` through blocker `TASK-417` / PR #387 to break the circular dependency between the stale-docs and dependency-audit full-gate failures; this branch verifies and closes the original promoted task.
- Canonical proof: all 17 full local-gate steps passed on the post-`TASK-417` baseline.

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
