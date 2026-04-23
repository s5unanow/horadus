# TASK-391: Close nested-helper docstring policy gap

## Status

- Owner: Codex
- Started: 2026-04-23
- Current state: In progress
- Planning Gates: Required — satisfying the newly enforced nested-helper policy requires touching allowlisted `src/workers/tasks.py`.

## Goal (1-3 lines)

Extend the scoped docstring-policy checker so nested helper functions on guarded
surfaces are enforced, then bring the newly surfaced guarded-worker helpers into
compliance without widening the policy beyond nested functions.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-391`)
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/docstring_policy.py`, `src/workers/tasks.py`, `tests/workflow/test_docstring_policy.py`, `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies: preserve existing policy semantics for module/class/member checks while adding nested-function traversal only

## Outputs

- Expected behavior/artifacts: nested function docstring enforcement on guarded surfaces, regression coverage, compliant guarded worker helpers, and aligned runbook guidance
- Validation evidence: targeted workflow tests, fast gate, integration proof, and canonical full local gate

## Non-Goals

- Explicitly excluded work: broader docstring-policy redesign, nested class-in-function enforcement, or refactoring `src/workers/tasks.py` beyond the minimal compliance docstrings

## Scope

- In scope: nested-function AST traversal, nested-helper regression tests, docstring fixes for newly surfaced guarded helpers, and runbook wording
- Out of scope: changing target selection in `config/quality/docstring_policy.toml` or re-scoping other guarded modules

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: recurse only through nested function definitions and reuse the existing requirement-reason logic instead of inventing a separate nested-helper rule set.
- Rejected simpler alternative: keep top-level-only traversal and document the loophole; that leaves complex guarded helper closures unenforced.
- First integration proof: `make test-integration-docker`
- Hotspot Outcome: keep-flat-with-rationale — `src/workers/tasks.py` is an allowlisted owner hotspot and this task only adds the minimal helper docstrings needed for compliance.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-04-23: Limit traversal expansion to nested functions so the task closes the documented loophole without silently broadening policy to nested classes inside function bodies. (reason: acceptance criteria target nested helper functions specifically)
- 2026-04-23: Fix the newly surfaced `src/workers/tasks.py` `_runner` closures in the same task instead of carving out a new exemption. (reason: guarded surfaces must actually satisfy the policy once the loophole is closed)
- 2026-04-23: Caller inventory for the shared workflow helper is `scripts/check_docstring_policy.py`, the `docstring-policy` full-local-gate step in `tools/horadus/python/horadus_workflow/task_workflow_gate_steps.py`, and the script/workflow regression suites under `tests/unit/scripts/`, `tests/horadus_cli/v2/`, and `tests/workflow/`. (reason: shared workflow behavior changes must keep unaffected callers covered)

## Risks / Foot-guns

- Nested traversal could accidentally widen enforcement beyond helpers -> recurse only through function bodies and keep the existing member-reason logic unchanged.
- Closing the loophole can surface pre-existing guarded-surface violations -> fix only the newly enforced guarded helpers needed to keep the gate green.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules: `tools/horadus/python/horadus_workflow/docstring_policy.py`, `src/workers/tasks.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
