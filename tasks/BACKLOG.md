# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-380`.
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

### TASK-365: Add Retrieval Behavior Evals for RFC-001 Context Surfaces
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

**Dependency Note**:
- Sequence after `TASK-288` approves the RFC-001 implementation queue.

As the repo adds markdown-first retrieval/context-pack behavior, measure
retrieval correctness the same way prompt/model work is measured: include the
active task/spec/policy context that should be retrieved, exclude
archived/non-authoritative docs by default, and keep the returned context set
minimal and phase-appropriate.

**Planning Gates**: Required — shared workflow/context-retrieval contract and policy surface
**Files**: `docs/rfc/001-agent-context-retrieval.md`, `tools/horadus/python/horadus_cli/`, `tools/horadus/python/horadus_workflow/`, `tests/`, `docs/AGENT_RUNBOOK.md`

**Acceptance Criteria**:
- [ ] Add behavior evals for include/exclude retrieval rules over live vs archived task documents
- [ ] Cover at least one minimal-context case so retrieval quality is not judged only by recall
- [ ] Eval artifacts state retrieval mode/phase and authoritative-source basis
- [ ] Workflow docs explain when retrieval behavior suites must run for context-pack or retrieval changes

---

### TASK-377: Close docstring-policy gap in make check
**Priority**: P2
**Estimate**: <1h

Promote the TASK-255 review follow-up that closes the gap between the new
scoped docstring-policy gate and the general local code-quality entrypoint.

**Files**: `Makefile`, `README.md`, `tests/horadus_cli/v2/test_task_workflow.py`

**Acceptance Criteria**:
- [ ] The canonical local 'make check' quality entrypoint includes the scoped docstring-policy gate, or the repo’s documented code-quality entrypoint is updated so contributors do not get a false local green.
- [ ] README and any repo-owned workflow documentation stay aligned with the actual code-quality command behavior.
- [ ] Regression coverage proves the workflow/config surfaces reflect the intended docstring-policy wiring.

---

### TASK-378: Accept completed hotspot follow-up task references
**Priority**: P2
**Estimate**: 1-2 hours

Promote the TASK-368 review follow-up that keeps hotspot planning history valid
after the referenced cleanup task has already been completed.

**Files**: `tools/horadus/python/horadus_workflow/_docs_freshness_planning_hotspots.py`, `tools/horadus/python/horadus_workflow/_docs_freshness_planning_artifacts.py`, `tests/workflow/test_docs_freshness_planning_hotspots.py`

**Acceptance Criteria**:
- [ ] Hotspot follow-up validation accepts distinct follow-up TASK ids that are either still open or already completed/archived.
- [ ] Unknown-task and same-task follow-up protections remain enforced.
- [ ] Regression coverage proves historical planning artifacts stay valid after the referenced cleanup task leaves the live backlog.

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
