# TASK-350: Add a Cyclomatic-Complexity Ratchet for Tracked Python Surfaces

## Status

- Owner: Codex
- Started: 2026-03-18
- Current state: In progress
- Planning Gates: Required — shared quality policy and repo-wide static-analysis behavior

## Goal (1-3 lines)

Extend the existing repo-owned code-shape checker so tracked Python functions
and methods also obey cyclomatic-complexity budgets. New code should fail
closed against default limits, while legacy hotspots remain explicit,
ratcheted, and reviewable in the same policy artifact.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-350`)
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `config/quality/code_shape.toml`
  - `scripts/check_code_shape.py`
  - `tools/horadus/python/horadus_workflow/code_shape.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `docs/AGENT_RUNBOOK.md`
  - `tests/workflow/test_code_shape.py`
  - `tests/unit/scripts/test_check_code_shape.py`
  - `tests/horadus_cli/v2/test_task_workflow.py`
- Preconditions/dependencies:
  - preserve the existing repo-owned code-shape model from `TASK-328`
  - keep `make agent-check`, the canonical full local gate, and CI aligned on
    the same checker entrypoint
  - keep thresholds and allowlisted exceptions reviewable in repo-owned config
    instead of hidden in linter defaults or broad per-file ignores

## Outputs

- Expected behavior/artifacts:
  - repo-owned complexity budgets added to `config/quality/code_shape.toml`
  - explicit member-level complexity ratchets for legacy hotspots that exceed
    the default budget today
  - extended code-shape analyzer and script output for complexity violations
    and stale overrides
  - updated workflow docs describing the stricter complexity contract
  - regression coverage for pass, fail, ratchet, and stale-override paths
- Validation evidence:
  - targeted workflow/checker tests
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Replacing the repo-owned checker with Ruff-only enforcement that cannot
  express ratcheted legacy exceptions narrowly
- Refactoring every existing complex function in the same task
- Introducing subjective maintainability scoring beyond deterministic
  cyclomatic-complexity counting
- Expanding release-gate contract changes beyond the already-wired code-shape
  entrypoint; broader gate alignment belongs to `TASK-353`

## Scope

- In scope:
  - define default member cyclomatic-complexity budgets for production and test
    code
  - record explicit legacy member complexity exceptions in the existing policy
    artifact
  - extend the repo-owned analyzer, rendering, and script surface
  - keep `Makefile`, lifecycle/local-gate helpers, and CI parity aligned
  - document the updated contract in operator-facing workflow docs
- Out of scope:
  - module-level complexity scoring
  - large cleanup refactors to remove every newly allowlisted hotspot
  - changing unrelated import-boundary or docs-freshness policy behavior

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Extend the existing code-shape analyzer and policy file
  rather than introducing a second linter entrypoint or a separate ratchet
  tool.
- `Anti-Abstraction Gate`: Reuse the current AST-based measurement flow and
  add only the minimum measurement/policy fields needed for cyclomatic
  complexity.
- `Integration-First Gate`:
  - Validation target: the existing `scripts/check_code_shape.py` entrypoint
    remains the single complexity-enforcing surface for `make agent-check`, the
    canonical full local gate, and CI.
  - Exercises: representative default-budget failures, explicit legacy
    exceptions, stale complexity overrides, and workflow parity checks.
- `Code Shape Gate`: Not triggered — the planned changes do not materially edit
  an allowlisted oversized Python hotspot from `config/quality/code_shape.toml`.
- `Determinism Gate`: Triggered — complexity must be computed deterministically
  from tracked Python ASTs and repo-owned thresholds.
- `LLM Budget/Safety Gate`: Not applicable — no runtime LLM behavior changes.
- `Observability Gate`: Triggered — failure output must identify the member,
  measured complexity, and governing default or allowlisted maximum.

## Shared Workflow/Policy Change Checklist

- Callers/config that depend on the current code-shape behavior:
  - `scripts/check_code_shape.py`
  - `Makefile` targets `agent-check` and `code-shape`
  - `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`
    (`full_local_gate_steps`)
  - `.github/workflows/ci.yml`
  - `docs/AGENT_RUNBOOK.md`
  - workflow parity tests in `tests/horadus_cli/v2/test_task_workflow.py`
- Unaffected-caller regression target:
  - keep the local-gate/CI parity assertions green while changing only the
    analyzer internals and policy data, so other task workflow entry points do
    not drift

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - add cyclomatic-complexity budgets and member override maxima to the
    existing code-shape policy artifact
  - compute complexity in the repo-owned AST analyzer so the ratchet model can
    stay explicit, narrow, and stale-override aware
  - continue enforcing through the existing `check_code_shape.py` script so the
    canonical gate contract does not split
- Rejected simpler alternative:
  - enabling Ruff McCabe alone would give a default cap, but it would not
    provide the same explicit per-member ratchet inventory, stale-override
    detection, or policy alignment with the repo-owned code-shape artifact
- First integration proof:
  - baseline the current repo to choose workable defaults, then make the
    extended checker pass only when legacy complexity inventory is explicitly
    recorded
- Waivers:
  - use member-level allowlisted maxima only where the current baseline still
    exceeds the default budget; treat those entries as ratchets, not blanket
    exemptions

## Plan (Keep Updated)

1. Baseline current function/method complexity across tracked Python surfaces
2. Choose default production/test complexity budgets and seed explicit legacy
   member overrides
3. Extend `config/quality/code_shape.toml` and the workflow analyzer data model
4. Add checker logic, failure rendering, and stale-override detection for
   member complexity
5. Update tests for analyzer behavior, script output, and unaffected
   workflow-caller parity
6. Update operator-facing workflow docs
7. Run targeted tests plus the canonical local gates and adjust only if the
   baseline proves the thresholds are unworkable

## Decisions (Timestamped)

- 2026-03-18: Keep cyclomatic-complexity enforcement inside the repo-owned
  code-shape checker instead of adding a second enforcement path.
- 2026-03-18: Scope the first pass to function/method complexity because that
  addresses branch-heavy logic directly without adding noisier module-level
  scoring.
- 2026-03-18: Use separate production/test default budgets so the contract
  stays strict for runtime code without forcing a large test cleanup sweep in
  the same task.
- 2026-03-18: Start with default member-complexity budgets of `18` for
  production/tooling/scripts and `20` for tests, then seed only the current
  outliers as explicit ratcheted overrides.

## Risks / Foot-guns

- Complexity counting can drift from operator expectations if the AST rules are
  undocumented or surprising -> keep the counted constructs limited and test
  them directly
- Thresholds that are too strict create a large waiver inventory -> baseline
  the repo first and choose defaults that tighten health without producing
  noise-heavy policy churn
- Broad allowlists could become permanent debt -> fail stale overrides once a
  function drops back under the default budget
- Workflow drift can appear if only analyzer tests change -> keep parity tests
  for `Makefile`, lifecycle local gate, and CI green

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-350`
- targeted `pytest` for the code-shape analyzer, script entrypoint, and task
  workflow parity
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Related prior task:
  - `tasks/specs/328-add-code-shape-guardrails-to-prevent-module-sprawl.md`
  - `tasks/exec_plans/TASK-328.md`
