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
