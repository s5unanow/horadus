# TASK-285: Shared Workflow Guardrails

## Status

- Owner: Codex
- Started: 2026-03-09
- Current state: In progress

## Goal (1-3 lines)

Add narrow repo-owned guardrails for future workflow/policy changes so shared
helper edits require caller audits and unaffected-caller regression coverage,
and review-gate policy edits require explicit current-head/current-window
semantics.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-285`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/core/repo_workflow.py`, `src/core/docs_freshness.py`
- Preconditions/dependencies: canonical Horadus workflow branch start completed

## Outputs

- Expected behavior/artifacts:
  - canonical workflow surfaces include the new shared-workflow guardrails
  - `tasks/specs/TEMPLATE.md` includes an applicability-scoped checklist for
    shared workflow/policy changes
  - docs-freshness enforces the new statements
- Validation evidence:
  - targeted docs-freshness unit tests
  - `uv run --no-sync horadus tasks local-gate --full`

## Non-Goals

- Explicitly excluded work:
  - changing merge/review-gate behavior itself
  - broad prompt-writing or process requirements unrelated to workflow/policy
    changes
  - implementing `TASK-286`

## Scope

- In scope:
  - central canonical statements for caller-audit and review-signal semantics
  - docs/runbook/skill/template alignment
  - docs-freshness enforcement and regression tests
- Out of scope:
  - new CLI commands
  - changes to remote review automation contracts

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-09: Keep the new guidance limited to workflow/policy changes and
  enforce it only on canonical agent-facing surfaces, not repo-wide prose.

## Risks / Foot-guns

- Shared guidance duplication can drift -> centralize statements in
  `src/core/repo_workflow.py` and enforce with docs-freshness.
- Template changes can become boilerplate -> make the checklist explicitly
  conditional on shared workflow/policy edits.

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_docs_freshness.py -q`
- `uv run --no-sync python scripts/check_docs_freshness.py`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none (backlog-driven task)
- Relevant modules: `src/core/repo_workflow.py`, `src/core/docs_freshness.py`
