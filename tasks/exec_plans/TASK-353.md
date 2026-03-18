# TASK-353: Align Canonical Release and Local Gates with the Full Repo-Owned Analyzer Set

## Status

- Owner: Codex
- Started: 2026-03-18
- Current state: In progress
- Planning Gates: Required — shared workflow/policy gate contract change

## Goal (1-3 lines)

Make the repo-owned analyzer contract explicit and consistent across the fast
iteration gate, the canonical full local gate, and `make release-gate`. The
strict release path should extend the canonical full gate instead of
redefining a narrower, partially overlapping analyzer set.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-353`)
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `scripts/validate_assessment_artifacts.py`
  - `src/eval/audit.py`
  - `docs/AGENT_RUNBOOK.md`
  - `docs/RELEASING.md`
  - `docs/ASSESSMENTS.md`
  - `ai/eval/README.md`
  - `tests/horadus_cli/v2/test_task_workflow.py`
  - `tests/unit/scripts/test_validate_assessment_artifacts.py`
- Preconditions/dependencies:
  - keep `agent-check` meaningfully faster than the full local/release gates
  - preserve the repo-owned local-gate helper as the canonical strict contract
  - avoid introducing a second gate-definition surface when the current
    workflow helper can own the authoritative full-step list

## Outputs

- Expected behavior/artifacts:
  - canonical full local gate includes the maintained repo-owned analyzers that
    were previously only opt-in
  - `make release-gate` reuses the canonical full local gate and then applies
    release-only checks
  - `agent-check` includes any lightweight analyzer needed to protect trusted
    repo artifacts without taking on the entire release contract
  - docs and parity tests describe the resulting contract clearly
- Validation evidence:
  - targeted workflow/config tests for local-gate, Makefile, and CI parity
  - targeted validator tests for any new analyzer invocation path
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Changing the taxonomy-validation mode from the current transitional
  `subset`/`warn` policy
- Expanding release-gate runtime/SLO semantics or post-deploy checks
- Replacing Make targets and CI jobs with a new workflow runner abstraction
- Making exploratory eval benchmark runs mandatory for every engineering task

## Scope

- In scope:
  - inventory the current repo-owned analyzer/validator set and assign each to
    `agent-check`, the canonical full local gate, or release-only follow-on
    validation
  - promote missing analyzers for assessment/eval artifact trust into enforced
    gates where they belong
  - make `release-gate` depend on the canonical full local gate instead of a
    hand-maintained subset
  - update CI and workflow docs so the stricter contract is explicit and tested
- Out of scope:
  - redesigning the task workflow CLI surface beyond the existing gate helpers
  - changing unrelated workflow sequencing, review-gate, or merge behavior
  - adding new analyzers that are not already repo-owned

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: extend the existing repo-owned full local gate and the
  existing Make/CI entry points instead of creating another orchestration
  layer.
- `Anti-Abstraction Gate`: keep the authoritative strict analyzer list in the
  current workflow helper and use tests to keep Make/CI wrappers aligned,
  rather than inventing a general plugin system for a small fixed step set.
- `Integration-First Gate`:
  - Validation target: the canonical local gate, `make release-gate`, and CI
    parity assertions all reflect the same analyzer inventory.
  - Exercises: step inventory, release-gate composition, and at least one
    unaffected workflow caller that still relies on the same helper outputs.
- `Code Shape Gate`: Not triggered — the planned edits do not materially touch
  an allowlisted oversized Python hotspot.
- `Determinism Gate`: Triggered — analyzer inclusion must stay deterministic and
  repo-owned rather than operator-dependent.
- `LLM Budget/Safety Gate`: Not applicable — this changes validation policy, not
  runtime LLM execution.
- `Observability Gate`: Triggered — gate surfaces and docs must state which
  analyzers run where so failures are explainable.

## Shared Workflow/Policy Change Checklist

- Callers/config that depend on the current gate contract:
  - `Makefile` targets `agent-check`, `validate-assessments`,
    `validate-taxonomy-eval`, `audit-eval`, `local-gate`, and `release-gate`
  - `tools/horadus/python/horadus_workflow/task_workflow_lifecycle.py`
    (`full_local_gate_steps` and `local_gate_data`)
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
    (canonical command guidance surfaced to agents)
  - `.github/workflows/ci.yml`
  - `docs/AGENT_RUNBOOK.md`
  - `docs/RELEASING.md`
  - `docs/ASSESSMENTS.md`
  - `ai/eval/README.md`
  - workflow parity tests in `tests/horadus_cli/v2/test_task_workflow.py`
- Unaffected-caller regression target:
  - preserve `horadus tasks local-gate --full` dry-run/reporting behavior while
    expanding the enforced analyzer list, so downstream workflow commands keep
    their existing interface and only the step inventory changes

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - treat the repo-owned full local gate as the authoritative strict analyzer
    contract
  - make `make release-gate` call that contract and then add release-only
    checks such as migration drift
  - promote the repo-owned eval dataset audit into the full gate where release
    quality should fail closed
  - keep the raw assessment-artifact validator standalone because it targets
    untracked advisory automation output rather than canonical repo-owned
    release artifacts
- Rejected simpler alternative:
  - documenting the missing analyzers without wiring them into enforced gates
    would leave the same drift problem in place
- First integration proof:
  - targeted tests show the new step list, Makefile, and CI expectations align
    before running the broader local gates
- Waivers:
  - keep benchmark-style prompt evaluation optional because it is not a
    repo-wide analyzer for every engineering change; only the repo-owned audit
    and taxonomy validation are candidates for baseline enforced gates

## Plan (Keep Updated)

1. Record the current gate inventory and missing enforced analyzers
2. Update the canonical full local gate step list and any fast-gate additions
3. Recompose `make release-gate` around the canonical full gate plus
   release-only checks
4. Update CI/docs/tests to assert the same analyzer contract
5. Run targeted tests, then `make agent-check`, then the canonical full local
   gate
6. Close ledgers and finish the task lifecycle through the Horadus workflow

## Decisions (Timestamped)

- 2026-03-18: Use the canonical full local gate as the single strict analyzer
  contract, with `release-gate` as an extension rather than a second partial
  definition.
- 2026-03-18: Keep `agent-check` intentionally smaller than the strict gate.
- 2026-03-18: Demote `validate_assessment_artifacts.py` from the canonical
  repo gates because it validates untracked advisory automation output under
  `artifacts/assessments/`; promote `horadus eval audit --fail-on-warnings`
  instead because it protects repo-owned eval provenance expectations.

## Risks / Foot-guns

- Adding too much to `agent-check` could make normal iteration sluggish ->
  keep heavy eval/migration/integration steps out of the fast gate
- Release-gate composition can drift again if tests only cover the local helper
  -> add parity assertions for Makefile and CI surfaces
- Enforcing validation for untracked local automation history would create
  non-reproducible local blockers -> keep the raw assessment validator
  standalone and document that rationale explicitly

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-353`
- targeted `pytest` for workflow parity/config coverage and validator behavior
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Canonical planning example:
  - `tasks/specs/275-finish-review-gate-timeout.md`
- Related repo-health tasks:
  - `tasks/exec_plans/TASK-350.md`
