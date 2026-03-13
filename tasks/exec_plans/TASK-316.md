# TASK-316: Decompose `_docs_freshness_checks.py` Into Focused Internal Modules

## Status

- Owner:
- Started: 2026-03-13
- Current state: In progress
- Planning Gates: Required — shared workflow validation code with multiple direct importers and high regression risk if rule ordering or helper ownership shifts

## Goal (1-3 lines)

Break `tools/horadus/python/horadus_workflow/_docs_freshness_checks.py` into
smaller focused internal modules so each rule family is easier to reason
about and test without changing the public docs-freshness surface.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-316`)
  - `tasks/CURRENT_SPRINT.md`
  - `AGENTS.md` shared-workflow guardrails
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `tools/horadus/python/horadus_workflow/_docs_freshness_checks.py`
  - `tools/horadus/python/horadus_workflow/_docs_freshness_*`
  - `scripts/check_docs_freshness.py`
  - `src/core/docs_freshness.py`
  - `tests/workflow/test_docs_freshness.py`
  - `tests/workflow/test_workflow_support.py`
- Preconditions/dependencies:
  - Keep issue ordering stable
  - Preserve override behavior and warning/error routing
  - Keep script and compatibility import surfaces unchanged

## Outputs

- Expected behavior/artifacts:
  - Focused internal docs-freshness modules grouped by rule family and orchestration
  - Compatibility-preserving `docs_freshness.py` facade and `_docs_freshness_checks.py` import surface
  - Regression coverage demonstrating unchanged public behavior
- Validation evidence:
  - `tests/workflow/test_docs_freshness.py` passes
  - `tests/workflow/test_workflow_support.py` passes
  - `scripts/check_docs_freshness.py` output remains compatible

## Non-Goals

- Explicitly excluded work:
  - New docs-freshness rules or policy changes
  - Rewording issue messages, changing levels, or altering result shapes
  - Unrelated cleanup in other workflow modules

## Scope

- In scope:
  - Extract a small runner/orchestrator
  - Split content-validation rules from workflow/policy rules
  - Isolate `PROJECT_STATUS` and `CURRENT_SPRINT` / human-blocker validation
  - Keep shared issue accumulation helpers internal and reusable
- Out of scope:
  - Changing script call sites beyond internal import rewiring
  - Changing planning-artifact validation behavior
  - Broader workflow package restructuring outside docs freshness

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep `docs_freshness.py` as the public facade and reduce `_docs_freshness_checks.py` to compatibility re-exports plus focused internal modules.
- Rejected simpler alternative:
  - Leaving the logic in one file with section comments would keep the current cognitive load and make isolated testing difficult.
- First integration proof:
  - `scripts/check_docs_freshness.py`, `src/core/docs_freshness.py`, and the workflow test suite already define the behavior that must remain stable.
- Waivers:
  - Small internal indirection is acceptable if it preserves imports and behavior.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Treat this as a new live task instead of reusing closed `TASK-315`. (reason: task ids are global and never reused, and the user requested repo-workflow compliance)
- 2026-03-13: Preserve both `docs_freshness.py` and `_docs_freshness_checks.py` import surfaces while moving rule families behind them. (reason: direct tests and compatibility shims already import through those paths)
- 2026-03-13: Keep `_docs_freshness_checks.py` as a compatibility import layer and move evaluation order into a dedicated runner module. (reason: the refactor target is the internal implementation shape, not the helper import surface)

## Risks / Foot-guns

- Issue ordering drift while splitting rule families -> keep the runner call order aligned with the previous monolith
- Moving helper ownership breaks direct imports -> keep compatibility re-exports in place
- Shared-workflow refactor changes script output unexpectedly -> validate via the script entrypoint in addition to tests

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-316`
- `uv run --no-sync pytest tests/workflow/test_docs_freshness.py -q`
- `uv run --no-sync pytest tests/workflow/test_workflow_support.py -q`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `uv run --no-sync ruff check tools/horadus/python/horadus_workflow/_docs_freshness_checks.py tools/horadus/python/horadus_workflow/_docs_freshness_config.py tools/horadus/python/horadus_workflow/_docs_freshness_content_rules.py tools/horadus/python/horadus_workflow/_docs_freshness_current_sprint.py tools/horadus/python/horadus_workflow/_docs_freshness_issue_helpers.py tools/horadus/python/horadus_workflow/_docs_freshness_project_status.py tools/horadus/python/horadus_workflow/_docs_freshness_runner.py tools/horadus/python/horadus_workflow/_docs_freshness_workflow_rules.py`

## Notes / Links

- Spec:
  - Backlog entry only; this exec plan is the authoritative planning artifact.
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `tools/horadus/python/horadus_workflow/_docs_freshness_checks.py`
  - `scripts/check_docs_freshness.py`
  - `src/core/docs_freshness.py`
  - `tests/workflow/test_docs_freshness.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
