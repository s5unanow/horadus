# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-384`.
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

### TASK-365: Add Retrieval Behavior Evals for RFC-001 Context Surfaces
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

**Dependency Note**:
- Sequence after `TASK-380`, `TASK-381`, and `TASK-382` expose the first
  implement-mode context surfaces, but before `TASK-383` switches canonical
  autonomous workflow callers to that mode.

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

### TASK-380: Add Implement-Mode Context-Pack Contract
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Add `horadus tasks context-pack TASK-XXX --mode implement --format json` as the
Phase 1 RFC-001 retrieval surface while preserving the current unflagged broad
context-pack output for compatibility. The first slice should extend existing
Horadus CLI/workflow helpers, not introduce a local index or external retrieval
service.

**Planning Gates**: Required — shared workflow/context-pack contract and caller-visible CLI behavior
**Files**: `tools/horadus/python/horadus_cli/`, `tools/horadus/python/horadus_workflow/`, `tests/horadus_cli/v2/`, `docs/AGENT_RUNBOOK.md`, `docs/rfc/001-agent-context-retrieval.md`

**Acceptance Criteria**:
- [ ] Add a mode-aware context-pack CLI contract with `default` and `implement` modes
- [ ] Preserve the current unflagged text/JSON context-pack behavior
- [ ] Implement-mode JSON includes mode metadata, task metadata, excluded-source notes, and a compact code-backed policy payload
- [ ] Define the explicit curated legacy policy registry used by implement mode without requiring policy-doc front matter
- [ ] Add regression coverage for the new mode and for unchanged default behavior

---

### TASK-381: Add Retrieval Metadata and Canonical Spec Resolution
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Adopt the RFC-001 task-spec metadata slice without expanding the migration to
all policy docs. New or touched task specs should be able to declare retrieval
metadata, while legacy specs continue through deterministic fallback rules.

**Planning Gates**: Required — shared task/spec retrieval contract and docs validation behavior
**Files**: `tasks/specs/TEMPLATE.md`, `tools/horadus/python/horadus_workflow/`, `tests/horadus_cli/v2/`, `tests/workflow/`, `docs/rfc/001-agent-context-retrieval.md`

**Acceptance Criteria**:
- [ ] Update the task spec template with task-spec front matter fields and retrieval-ready guidance
- [ ] Parse structured backlog `**Spec**:` references as the primary legacy spec selector
- [ ] Fail closed in implement mode when multiple canonical spec candidates remain ambiguous
- [ ] Add supersession metadata rules for retrieval-ready specs
- [ ] Keep policy-doc front matter out of Phase 1 enforcement

---

### TASK-382: Add Task-Scoped Sprint Orientation and Test Candidates
**Priority**: P1 (High)
**Estimate**: 2-4 hours

Make implement-mode context smaller and more actionable by exposing a
task-scoped `CURRENT_SPRINT.md` extract, compact orientation metadata, explicit
human-gated/autonomous eligibility, and deterministic derived test candidates.

**Planning Gates**: Required — shared workflow/context-pack contract and task-ledger extraction behavior
**Files**: `tasks/CURRENT_SPRINT.md`, `tools/horadus/python/horadus_workflow/`, `tests/horadus_cli/v2/`, `docs/AGENT_RUNBOOK.md`, `docs/rfc/001-agent-context-retrieval.md`

**Acceptance Criteria**:
- [ ] Implement-mode JSON exposes derived `task_status` and `autonomous_eligible`
- [ ] Human-gated tasks are excluded or explicitly blocked for autonomous implement-mode callers
- [ ] `CURRENT_SPRINT.md` retrieval returns the task line, applicable blocker metadata, and relevant sprint constraints without the full sprint file
- [ ] Add compact orientation metadata for `CURRENT_SPRINT.md`, `docs/ARCHITECTURE.md`, and `docs/DATA_MODEL.md`
- [ ] Derive test candidates from normalized declared task paths with labeled `match_reason` values

---

### TASK-383: Switch Agent Workflow Surfaces to Implement Context-Pack Mode
**Priority**: P1 (High)
**Estimate**: 2-4 hours

After implement-mode payloads and retrieval behavior evals exist, switch the
canonical agent-facing workflow surfaces from plain `context-pack` to
`context-pack --mode implement` for implementation work. Keep human-oriented
default context-pack output intact.

**Planning Gates**: Required — shared workflow guidance and command registry behavior
**Files**: `AGENTS.md`, `README.md`, `docs/AGENT_RUNBOOK.md`, `ops/skills/horadus-cli/`, `tools/horadus/python/horadus_workflow/repo_workflow.py`, `tests/horadus_cli/v2/`, `tests/workflow/`

**Acceptance Criteria**:
- [ ] Enumerate every current plain `context-pack` implementation workflow caller before switching commands
- [ ] Update canonical agent-facing workflow docs, skills, and command registries to use implement mode for implementation work
- [ ] Keep default unflagged `context-pack` available for human broad-context usage
- [ ] Add regression coverage for at least one updated canonical caller and one unaffected caller
- [ ] Document when retrieval behavior evals must run for future context-pack changes

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
