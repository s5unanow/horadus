# Backlog

Open task definitions only. Completed task history lives in `tasks/COMPLETED.md`, and detailed historical planning ledgers live under `archive/`.

---

## Task ID Policy

- Task IDs are global and never reused.
- Completed IDs are reserved permanently and tracked in `tasks/COMPLETED.md`.
- Next available task IDs start at `TASK-370`.
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

### TASK-363: Add Behavior-Oriented Eval Suites for High-Risk LLM Safety Paths
**Priority**: P1 (High)
**Estimate**: 4-6 hours

Current gold-set benchmarking and replay gates protect aggregate quality, but
they do not directly encode several production behaviors the runtime must
preserve: fail-closed taxonomy mapping, degraded-mode provisional writes, report
grounding/uncertainty contracts, and safe cache/runtime invalidation. Add a
behavior-oriented eval layer with small tagged suites that measure those
contracts directly.

**Planning Gates**: Required — shared eval harness and release-gate behavior across prompt/runtime surfaces
**Files**: `src/eval/`, `tools/horadus/python/horadus_cli/`, `ai/eval/`, `docs/PROMPT_EVAL_POLICY.md`, `docs/AGENT_RUNBOOK.md`, `tests/`

**Acceptance Criteria**:
- [ ] Add tagged behavior suites for at least taxonomy safety, degraded-mode safety, and report grounding
- [ ] Each behavior eval records the production contract it is measuring so failures map cleanly to intended agent/system behavior
- [ ] CLI/runtime supports running a targeted subset of behavior suites without requiring the full benchmark
- [ ] Prompt/model promotion docs explain when behavior suites are required in addition to the gold-set benchmark

---

### TASK-364: Build a Runtime-to-Eval Regression Intake Loop
**Priority**: P2 (Medium)
**Estimate**: 3-5 hours

Turn real runtime/operator failures into eval seeds instead of relying only on
handcrafted benchmark rows. Add a small workflow that converts selected
taxonomy-gap, replay-failure, grounding-violation, or operator-invalidation
artifacts into a reviewable regression-intake format with provenance and
redaction expectations.

**Planning Gates**: Not Required — scoped evaluation-data workflow improvement
**Files**: `src/eval/`, `tools/horadus/python/horadus_cli/`, `ai/eval/`, `docs/TRACING.md`, `ai/eval/README.md`, `tests/`

**Acceptance Criteria**:
- [ ] Define a repo-owned intake format for candidate regression cases with provenance metadata and redaction expectations
- [ ] Support collecting seeds from at least two existing failure surfaces
- [ ] Document the review flow for promoting an intake case into the gold set or a behavior suite
- [ ] Tests cover normalization and provenance handling without requiring network access

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

### TASK-366: Add a Code-Health Erosion Eval for Changed Python Surfaces
**Priority**: P1 (High)
**Estimate**: 4-6 hours

The repo now enforces static code-shape budgets, but those checks only answer
"does this snapshot fit the ratchet?" They do not measure whether an iterative
task made the touched code structurally worse even when line-count and
complexity budgets still technically pass. Add a repo-owned code-health eval
that compares changed Python surfaces against merge-base and emits a small,
deterministic structural-regression artifact for agent and reviewer use.

**Dependency Note**:
- Build on the existing `TASK-328` / `TASK-350` code-shape analyzers instead of
  introducing a second parser stack.

**Planning Gates**: Required — shared eval/tooling contract and new structural regression signal
**Files**: `tools/horadus/python/horadus_workflow/code_shape.py`, `src/eval/`, `tools/horadus/python/horadus_cli/`, `docs/AGENT_RUNBOOK.md`, `tests/`

**Acceptance Criteria**:
- [ ] Add a repo-owned `horadus eval code-health` command that compares an explicit base/head diff or the current branch against merge-base
- [ ] The artifact records per-file structural deltas for touched Python files using deterministic metrics derived from existing AST/code-shape signals
- [ ] The metric set includes at least one deterministic verbosity or duplication signal beyond raw line count and cyclomatic complexity so the eval can catch "more code, same behavior" regressions
- [ ] Reporting stays explainable: no opaque LLM scoring, and every flagged regression states which metric worsened
- [ ] Tests cover representative improve/flat/regress paths without requiring network access

---

### TASK-367: Ratchet Changed-File Code-Health Regressions in Local Gates
**Priority**: P1 (High)
**Estimate**: 3-5 hours

Once a code-health eval exists, use it as a ratchet on touched files instead of
waiting for long-horizon structural decay to become another allowlist entry.
Integrate the eval into the repo's quality workflow so authors get an early,
consistent signal when a branch makes changed code harder to extend, even when
the branch still passes ordinary tests and static thresholds.

**Dependency Note**:
- Sequence after `TASK-366`.

**Planning Gates**: Required — shared workflow/gate behavior across agent-check and canonical local validation
**Files**: `Makefile`, `tools/horadus/python/horadus_workflow/task_workflow_gate_steps.py`, `docs/AGENT_RUNBOOK.md`, `tests/`

**Acceptance Criteria**:
- [ ] `make agent-check` surfaces changed-file code-health results in a clear author-facing form
- [ ] `uv run --no-sync horadus tasks local-gate --full` fail-closes on touched-file structural regressions beyond the ratcheted policy
- [ ] Unchanged legacy hotspots do not fail merely for existing debt; only regressions on files in scope are blocked
- [ ] Tests cover no-op diffs, improving diffs, regressing diffs, and unaffected-file behavior

---

### TASK-368: Enforce Hotspot-Touch Debt Capture for Allowlisted Production Files
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

Current policy already says that materially touching an allowlisted oversized
Python file requires planning gates and an exec plan, but the required
"reduce/keep-flat/carry-forward debt" decision still lives mostly in narrative
discipline. Make that contract machine-checkable so tasks that touch
allowlisted production hotspots must explicitly record whether they reduced the
hotspot, kept it flat with rationale, or created a concrete follow-up cleanup
task.

**Dependency Note**:
- Extend the workflow policy introduced by `TASK-328`; do not widen the
  allowlist or create an escape hatch that bypasses the existing ratchet.

**Planning Gates**: Required — shared workflow/policy validation for planning artifacts and hotspot touches
**Files**: `AGENTS.md`, `tasks/specs/TEMPLATE.md`, `docs/AGENT_RUNBOOK.md`, `tools/horadus/python/horadus_workflow/_docs_freshness_planning.py`, `tools/horadus/python/horadus_workflow/task_workflow_query.py`, `tests/`

**Acceptance Criteria**:
- [ ] Planning artifacts for tasks that materially edit allowlisted production Python files must record one explicit hotspot outcome marker: reduce, keep-flat-with-rationale, or follow-up-task-created
- [ ] Repo-owned planning validation fails when the marker is required but missing
- [ ] The rule applies only to allowlisted production hotspots, not ordinary files or oversized tests
- [ ] Workflow docs explain the marker and show how to satisfy it during planning intake

---

### TASK-369: Make Local Pre-Push Review Slop-Aware for Changed Files
**Priority**: P2 (Medium)
**Estimate**: 2-4 hours

Static gates catch only the regressions that were encoded ahead of time. The
opt-in local-review path should also look explicitly for the iterative failure
modes the repo now cares about: hotspot expansion, concern sprawl inside
touched modules, and verbosity or duplication growth that may still pass the
ordinary gate stack. Tighten the local-review prompt contract so provider
feedback looks for those patterns consistently instead of relying on a generic
"bugs and tests" review prompt.

**Dependency Note**:
- Reuse the changed-file and branch-diff context already gathered by the local
  review harness, and consume `TASK-366` code-health output when available
  rather than inventing a second diff-analysis flow.

**Planning Gates**: Required — shared workflow/review contract across provider adapters and operator-facing guidance
**Files**: `tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py`, `tools/horadus/python/horadus_workflow/task_workflow_local_review.py`, `docs/AGENT_RUNBOOK.md`, `tests/`

**Acceptance Criteria**:
- [ ] The local-review prompt contract explicitly asks reviewers to flag hotspot expansion, multi-concern growth inside touched modules, and verbosity or duplication regressions in addition to ordinary bug-risk findings
- [ ] When changed-file code-health output is available, the local-review prompt includes or references that structural summary instead of asking providers to rediscover it from scratch
- [ ] The existing marker-line output contract and findings-first review format remain stable across providers
- [ ] Tests cover prompt rendering and provider-adapter behavior without requiring network access

---

## Future Ideas (Not Scheduled)

- [ ] Archive `tasks/specs/` or `tasks/exec_plans/` only if Sprint 4 still shows measurable context pressure after the live-ledger reset.
