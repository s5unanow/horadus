# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-397`.
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

### TASK-386: Fix task intake id allocation under concurrent writes
**Priority**: P1
**Estimate**: 1-2h

Observed on 2026-04-12 while adding multiple discussion follow-ups in parallel:
several concurrent 'horadus tasks intake add' invocations all reported success
with the same intake id (INTAKE-0004), but only one entry actually persisted.
Investigate id allocation and append/write semantics so concurrent intake
capture is either serialized safely or fails clearly instead of reporting
duplicate success.

**Files**: `tools/horadus/python/horadus_workflow/task_workflow_intake.py`, `tests`

**Acceptance Criteria**:
- [ ] Concurrent task-intake writes must not allocate the same intake id or silently drop entries.
- [ ] If safe serialization cannot proceed, the command must fail clearly instead of reporting duplicate success.
- [ ] Add focused regression coverage for concurrent intake id allocation and persistence behavior.

---

### TASK-387: Fail closed on spec files missing Planning Gates
**Priority**: P1
**Estimate**: 2-4h

Follow-up to TASK-368 review: planning validation currently skips task-owned
spec files that omit the Planning Gates marker unless another signal already
makes the task applicable. Make spec presence fail closed with a missing-marker
issue and add regression coverage for the reproduced tasks/specs/900-missing-
marker.md case.

**Files**: `tools/horadus/python/horadus_workflow/_docs_freshness_planning_artifacts.py`, `tests`

**Acceptance Criteria**:
- [ ] When a task-owned spec exists without a Planning Gates marker, planning validation must fail closed with a missing-marker issue.
- [ ] Add regression coverage for the reproduced missing-marker spec case and keep valid spec/backlog combinations green.

---

### TASK-388: Remove Any erasure from trend-write mutations
**Priority**: P1
**Estimate**: 2-4h

_trend_write_mutations.py discards ValidatedTrendWritePayload and related
concrete types with Any at privileged write boundaries, leaving the path
effectively unchecked

**Files**: `src/api/routes/_trend_write_contract.py`, `src/api/routes/_trend_write_mutations.py`, `tests`

**Acceptance Criteria**:
- [ ] Replace Any-erased privileged trend-write mutation payloads with concrete validated types through the mutation helpers.
- [ ] Keep the existing runtime validation path intact while improving static type safety and targeted regression coverage.

---

### TASK-389: Align Numeric ORM typing with Decimal semantics
**Priority**: P1
**Estimate**: 1-2d

Numeric-backed ORM fields are annotated as float while runtime already handles
Decimal values on probability, evidence, restatement, and cost paths

**Files**: `src/storage/models.py`, `src/storage/trend_state_models.py`, `src/storage/restatement_models.py`, `src/core/trend_engine.py`, `src/processing/cost_tracker.py`, `tests`

**Acceptance Criteria**:
- [ ] Numeric-backed ORM model annotations must reflect Decimal-backed runtime semantics across the touched storage/domain surfaces.
- [ ] Make boundary conversions explicit where needed and update targeted typing/tests so float-vs-Decimal drift does not regress silently.

---

### TASK-390: Add dirty-main watchdog for agent sessions
**Priority**: P2
**Estimate**: 1-3h

Add a lightweight safeguard that detects tracked diffs on main during
agent/chat sessions and surfaces a clear workflow violation. Candidate surface
could be a Horadus assert-safe-worktree check, automation, or app-integrated
watchdog.

**Files**: `tools/horadus/python/horadus_workflow`, `docs/AGENT_RUNBOOK.md`, `AGENTS.md`, `tests`

**Acceptance Criteria**:
- [ ] Add a repo-owned guardrail that detects tracked diffs on main for chat/agent work and reports a clear workflow violation.
- [ ] Document the intended surface and add focused regression coverage for the guardrail behavior.

---

### TASK-391: Close nested-helper docstring policy gap
**Priority**: P2
**Estimate**: 1-2h

Follow-up to TASK-255 review: the scoped docstring-policy checker skips nested
functions entirely, so complex inner helpers on guarded paths do not require
docstrings. Extend the AST walk and regression coverage so complex nested
helpers cannot bypass the policy.

**Files**: `tools/horadus/python/horadus_workflow/docstring_policy.py`, `tests/workflow/test_docstring_policy.py`

**Acceptance Criteria**:
- [ ] Scoped docstring policy must cover nested helper functions on guarded surfaces, not only top-level functions and class members.
- [ ] Add regression coverage for both failing and compliant nested-helper cases.

---

### TASK-392: Fix root horadus help and runbook freshness drift
**Priority**: P2
**Estimate**: 1-3h

root CLI help advertises subcommands it does not describe, and
docs/AGENT_RUNBOOK.md carries a stale Last Verified marker without freshness
enforcement

**Files**: `docs/AGENT_RUNBOOK.md`, `tools/horadus/python/horadus_workflow/docs_freshness.py`, `tools/horadus/python/horadus_cli`

**Acceptance Criteria**:
- [ ] Root horadus help output and the runbook command index must agree on the advertised command surface.
- [ ] Add or extend freshness enforcement so docs/AGENT_RUNBOOK.md cannot keep a stale Last Verified marker unnoticed.

---

### TASK-393: Sync API docs with runtime contracts
**Priority**: P2
**Estimate**: 2-4h

docs/API.md and README.md drift from live privileged-write and split event-
state contracts; examples omit required headers and docs still present legacy
lifecycle as primary

**Files**: `docs/API.md`, `README.md`, `src/api/routes/_privileged_write_contract.py`, `src/api/routes/events.py`

**Acceptance Criteria**:
- [ ] docs/API.md and README.md must match live privileged-write header requirements and split event-state/runtime filter contracts.
- [ ] Update the affected examples and operator-facing docs so the documented API surface no longer points to legacy lifecycle semantics as primary.

---

### TASK-394: Design worktree isolation for Codex App task sessions
**Priority**: P2
**Estimate**: 1-2d

Design a chat-friendly worktree strategy for Codex App so each agent/task runs
in an isolated disposable worktree rather than the canonical main checkout.
Emphasis: containment of accidental edits and compatibility with the existing
Horadus task lifecycle.

**Files**: `AGENTS.md`, `docs/AGENT_RUNBOOK.md`, `ops/automations/specs`, `tasks/specs`

**Acceptance Criteria**:
- [ ] Produce a concrete repo-owned design/spec for worktree-isolated Codex chat sessions that fits the existing Horadus task lifecycle.
- [ ] Cover containment goals, lifecycle integration points, cleanup/ownership implications, and a staged rollout recommendation.

---

### TASK-396: Upgrade python-dotenv to 1.2.2 for dependency audit parity
**Priority**: P1
**Estimate**: 0.5-1h

TASK-386 local-gate blocks at dependency-audit because origin/main and this
branch both lock python-dotenv 1.2.1, while the audit now requires 1.2.2 for
CVE-2026-28684 remediation. Handle as a separate dependency update task/branch
so TASK-386 stays scope-pure.

**Files**: `pyproject.toml`, `uv.lock`

**Acceptance Criteria**:
- [ ] Dependency audit passes without a python-dotenv vulnerability finding.
- [ ] Lockfile and dependency metadata resolve python-dotenv to 1.2.2 or newer without introducing new audit failures.

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
