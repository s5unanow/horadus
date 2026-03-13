# TASK-315: Split `docs_freshness.py` Into Focused Workflow Modules

## Status

- Owner:
- Started: 2026-03-13
- Current state: Not started
- Planning Gates: Required — shared workflow validation code with many direct tests/importers and high regression risk if helpers move carelessly

## Goal (1-3 lines)

Break `tools/horadus/python/horadus_workflow/docs_freshness.py` into smaller,
focused workflow modules so parsing, planning-state resolution, validation, and
rendering can be understood and tested independently without changing any
external entrypoint or output contract.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-315`)
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md` shared-workflow guardrails
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `src/core/docs_freshness.py`
  - `scripts/check_docs_freshness.py`
  - `tests/workflow/test_docs_freshness.py`
  - `tests/workflow/test_workflow_support.py`
- Preconditions/dependencies:
  - Keep the current `run_docs_freshness_check` behavior and issue ordering stable
  - Preserve the repo-facing script and compatibility import surface
  - Avoid changing user-facing CLI/workflow wording unless existing tests already permit it

## Outputs

- Expected behavior/artifacts:
  - A focused internal module layout under `tools/horadus/python/horadus_workflow/`
  - A thin compatibility-preserving `docs_freshness.py` entry surface
  - Updated tests that validate the extracted seams without changing behavior
- Validation evidence:
  - Existing workflow docs-freshness tests still pass
  - At least one compatibility import test remains green
  - Targeted tests for extracted helpers where useful

## Non-Goals

- Explicitly excluded work:
  - New docs-freshness rules or policy changes
  - Rewording current issue messages, levels, or public result shapes
  - Unrelated cleanup across other workflow modules

## Scope

- In scope:
  - Separate parsing/helpers from validation logic
  - Separate planning-artifact discovery/state resolution from rule evaluation
  - Separate issue/result assembly and rendering helpers from raw checks
  - Re-export the public API from the existing module path
- Out of scope:
  - Changing the shell script or workflow call sites beyond import rewiring
  - Altering override file semantics or task-planning policy behavior
  - Broader workflow package reorganization beyond the docs-freshness surface

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `docs_freshness.py` as the public facade and move internal concerns behind narrowly named sibling modules.
- Rejected simpler alternative:
  - Section comments inside the current file would leave parsing, state resolution, validation, and rendering tightly coupled and still hard to test in isolation.
- First integration proof:
  - `scripts/check_docs_freshness.py`, `src/core/docs_freshness.py`, and `tests/workflow/test_docs_freshness.py` already define the compatibility surface that must stay stable.
- Waivers:
  - A small amount of re-export indirection is acceptable if it keeps existing imports untouched while making internal modules testable.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Treat this as a planning-gated shared-workflow refactor because the module is imported directly by runtime-compatibility shims, scripts, and a large workflow test suite. (reason: careless helper moves can silently break unaffected callers)
- 2026-03-13: Preserve the existing `docs_freshness.py` module path as a compatibility facade instead of forcing a repo-wide import cutover. (reason: the user asked for unchanged external entrypoints and semantics)

## Risks / Foot-guns

- Issue ordering changes while splitting checks -> keep the top-level evaluation order stable and regression-test key output sequences.
- Tests keep patching only the facade and miss internal regressions -> add targeted tests at the extracted-module seam where it buys confidence.
- Shared constants/functions move into multiple files inconsistently -> define stable ownership for parsing, planning, validation, and rendering concerns before code motion.

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-315`
- `pytest tests/workflow/test_docs_freshness.py -v`
- `pytest tests/workflow/test_workflow_support.py -v`
- `python scripts/check_docs_freshness.py`

## Notes / Links

- Spec:
  - Backlog entry only; this exec plan is the authoritative planning artifact.
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `src/core/docs_freshness.py`
  - `scripts/check_docs_freshness.py`
  - `tests/workflow/test_docs_freshness.py`
  - `tests/workflow/test_workflow_support.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
