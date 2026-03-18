# TASK-349: Add repo-wide dependency direction gates for `src/` and tooling adapter seams

## Status

- Owner: Codex
- Started: 2026-03-18
- Current state: In progress
- Planning Gates: Required — shared workflow/policy quality gate for repo-wide import rules

## Goal (1-3 lines)

Add a repo-owned dependency-direction analyzer that enforces the intended `src/`
layering and the explicit `tools` to `src` runtime bridge seam. The gate should
fail closed on new reverse-direction imports, cycles, and tooling leaks.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-349`)
  - `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  - `src/`
  - `tools/horadus/python/`
  - `tests/workflow/`
  - `tests/horadus_cli/`
  - `docs/ARCHITECTURE.md`
  - `docs/AGENT_RUNBOOK.md`
- Preconditions/dependencies:
  - Preserve the documented runtime bridge at
    `tools/horadus/python/horadus_app_cli_runtime.py`
  - Reuse the existing workflow-test gate shape instead of inventing a separate
    ad hoc enforcement path

## Outputs

- Expected behavior/artifacts:
  - Explicit repo-owned contract for allowed `src` package dependencies
  - Explicit deny-by-default tools-to-app import policy with a narrow runtime bridge allowlist
  - Analyzer/reporting surface reusable from workflow tests
  - Regression tests for pass, forbidden edge, cycle, and tooling seam failures
- Validation evidence:
  - Targeted workflow/CLI tests
  - `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - Broad architecture refactors to eliminate currently legal dependencies
  - Rewiring the Horadus CLI runtime bridge design
  - Promoting every repo-owned analyzer into every release/local gate path in this task

## Scope

- In scope:
  - `src` package dependency contract
  - Tooling adapter seam contract
  - Cycle detection for the analyzed module graph
  - Workflow/docs updates needed to describe the new gate
- Out of scope:
  - New runtime features
  - Non-Python dependency analysis
  - Backlog triage beyond this task

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Extract the existing import-boundary check into a reusable workflow analyzer
    module and keep enforcement in the repo-owned workflow test surface.
- Rejected simpler alternative:
  - Expanding a single hard-coded test with more inline assertions would keep the
    policy opaque and make future caller reuse harder.
- First integration proof:
  - Workflow tests should fail on synthetic forbidden edges/cycles and pass on
    the live repo graph with the explicit runtime bridge allowlist.
- Waivers:
  - None planned; if the live graph needs an exception, keep it narrow and
    documented in the analyzer config with rationale.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement analyzer + explicit contract
3. Validate targeted tests and fast gate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-18: Use a reusable analyzer module under `horadus_workflow` and keep
  the enforcement entrypoint in `tests/workflow/test_import_boundaries.py`
  (matches the repo’s current workflow-analyzer pattern).
- 2026-03-18: Treat `tools/horadus/python/horadus_app_cli_runtime.py` as the
  only default-allowed tooling import seam into `src`, with explicit package
  allowlisting rather than a broad tooling exemption.

## Risks / Foot-guns

- Existing live imports may already violate the intended architecture ->
  derive the initial contract from the live graph and only fail on newly
  forbidden edges without open-ended waivers.
- Overly broad tools allowlist could nullify the seam guard ->
  keep the runtime bridge path-specific and package-scoped.
- Cycle detection could mis-handle package imports or `__init__` modules ->
  test synthetic cycle fixtures directly instead of trusting only the live graph.

## Validation Commands

- `uv run --no-sync pytest tests/workflow/test_import_boundaries.py -v -m unit`
- `uv run --no-sync pytest tests/horadus_cli/ -v -m unit`
- `make agent-check`

## Notes / Links

- Spec: backlog-only task; exec plan is the planning artifact
- Relevant modules:
  - `tests/workflow/test_import_boundaries.py`
  - `tools/horadus/python/horadus_workflow/`
  - `tools/horadus/python/horadus_app_cli_runtime.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
