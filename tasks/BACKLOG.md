# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-363`.
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

### TASK-334: Align Gemini local-review approval-mode flags with installed CLI
**Priority**: P3 (Low)
**Estimate**: <1h

The current Gemini local-review wrapper passes `--approval-mode plan`, but the
installed Gemini CLI warns that this mode requires an experimental flag and
falls back to the default approval mode. Normalize the wrapper to the installed
CLI contract so local-review avoids unnecessary compatibility noise.

**Planning Gates**: Not Required — narrow local-review compatibility follow-up
**Files**: `tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py`, `tests/horadus_cli/v2/test_task_local_review.py`

**Acceptance Criteria**:
- [ ] Reproduce the current Gemini approval-mode warning against the installed CLI
- [ ] Update the Gemini local-review wrapper to avoid unsupported approval-mode flags on the installed CLI
- [ ] Keep Claude and Codex local-review provider behavior unchanged

---

### TASK-189: Restrict `/health` and `/metrics` exposure outside development [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Reduce unauthenticated reconnaissance risk by restricting detailed health and
metrics endpoints outside development environments, while preserving a minimal
unauthenticated liveness endpoint.

**Assessment-Ref**:
- `artifacts/assessments/security/daily/2026-03-02.md` (`FINDING-2026-03-02-security-public-health-metrics`)

**Dependency Note**:
- Reuse the privileged-route policy from `TASK-200` rather than defining a
  second standalone authorization model for operational endpoints.

**Exec Plan**: Required (`tasks/exec_plans/README.md`)
**Files**: `src/api/middleware/auth.py`, `src/api/routes/health.py`, `src/api/routes/metrics.py`, `docs/DEPLOYMENT.md`, `tests/`

**Acceptance Criteria**:
- [ ] `/health` and `/metrics` are not publicly accessible in non-development environments (policy: admin-auth or explicit private-network-only)
- [ ] `/health/live` remains minimal and unauthenticated (coarse “up” only)
- [ ] Externally reachable health responses do not include raw exception strings or dependency internals
- [ ] Tests cover status codes and payload shapes for dev vs production-like profiles
- [ ] Human sign-off recorded before merge

---

### TASK-190: Harden admin-key compare + API key store file permissions [REQUIRES_HUMAN]
**Priority**: P2 (Medium)
**Estimate**: 1-2 hours

Eliminate timing side-channel risk in admin-key checks and ensure persisted API
key store files are written with restrictive permissions regardless of host
umask.

**Assessment-Ref**:
- `artifacts/assessments/security/daily/2026-03-02.md` (`FINDING-2026-03-02-security-admin-key-compare`)
- `artifacts/assessments/security/daily/2026-03-02.md` (`FINDING-2026-03-02-security-api-key-store-permissions`)

**Files**: `src/api/routes/auth.py`, `src/core/api_key_manager.py`, `docs/OPERATIONS.md`, `tests/`

**Acceptance Criteria**:
- [ ] Replace direct string equality with `secrets.compare_digest(...)` for admin key comparisons
- [ ] Enforce `0600` permissions on persisted key store temp + final files (best-effort cross-platform)
- [ ] Validate parent directory permissions (`0700`) where feasible and fail closed (or emit a high-severity warning) when hardening cannot be applied
- [ ] Tests cover: compare primitive, permission enforcement behavior, and failure/warn paths
- [ ] Human sign-off recorded before merge

### TASK-255: Add a Targeted Docstring Quality Gate for High-Value Surfaces
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours

Detailed code explanations are valuable in complex domain logic, but blanket
“document every function exhaustively” rules would create noise and stale prose.
Add an automated docstring policy for the parts of the codebase where it
actually improves agent and human comprehension.

**Files**: `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `src/core/`, `src/processing/`, `src/workers/`, `docs/AGENT_RUNBOOK.md`, `tests/`

**Acceptance Criteria**:
- [ ] Define a scoped docstring policy covering module docs, public APIs, and complex algorithms/invariants in selected high-value paths
- [ ] Add an automated check for that scoped policy in local and/or CI quality gates
- [ ] Avoid forcing exhaustive comments for trivial private helpers where names and types are already sufficient
- [ ] Document when to prefer docstrings versus short inline comments versus no extra prose

---

### TASK-288: Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue [REQUIRES_HUMAN]
**Priority**: P1 (High)
**Estimate**: 1-2 hours
**Spec**: `tasks/specs/288-rfc-001-implementation-breakdown.md`

Convert `docs/rfc/001-agent-context-retrieval.md` into an approved set of
implementation tasks with clear sequencing, but require explicit human review
before finalizing that execution queue. This task is human-gated because it
decides how the RFC becomes actual repo work and may change scope boundaries,
priorities, and rollout order.

**Files**: `tasks/BACKLOG.md`, `tasks/CURRENT_SPRINT.md`, `tasks/specs/288-rfc-001-implementation-breakdown.md`, `docs/rfc/001-agent-context-retrieval.md`

**Acceptance Criteria**:
- [ ] RFC-001 is decomposed into concrete implementation-task candidates with clear scope boundaries
- [ ] The proposed breakdown identifies any human decisions needed for sequencing or scope cuts
- [ ] The task stops for human review/approval before finalizing the follow-up execution queue

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
