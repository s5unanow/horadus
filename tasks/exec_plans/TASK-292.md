# TASK-292: Right-Size Live Task Ledgers and Archive Historical Planning Surfaces

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: In progress

## Goal (1-3 lines)

Close Sprint 3 early, archive the oversized planning ledgers, and reduce live
agent context to compact current/backlog/completed surfaces plus an archive
pointer stub.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-292`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/horadus_cli/task_repo.py`, `src/horadus_cli/task_commands.py`, `src/core/docs_freshness.py`
- Preconditions/dependencies: Preserve existing `TASK-291` intake edits while moving from `main` to `codex/task-292-ledger-archive-reset`

## Outputs

- Expected behavior/artifacts:
  - `archive/2026-03-10-sprint-3-close/` contains the pre-reset planning history
  - live planning surfaces are compact and authoritative
  - CLI task history lookup is live-only by default and archive-aware only with an explicit flag
  - docs-freshness enforces the new stub/archive contract
- Validation evidence:
  - targeted CLI and docs-freshness unit tests
  - `scripts/check_docs_freshness.py`

## Non-Goals

- Explicitly excluded work:
  - archiving `tasks/specs/` or `tasks/exec_plans/`
  - changing assessment-grounding rules away from `tasks/CURRENT_SPRINT.md`

## Scope

- In scope:
  - archive tree creation and sprint-history migration
  - live ledger rewrites
  - agent/doc guidance updates
  - archive-aware CLI lookup and docs-freshness enforcement
- Out of scope:
  - broader task taxonomy redesign
  - workflow behavior unrelated to task-history retrieval

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-10: Close Sprint 3 immediately and open Sprint 4 with a 14-day window ending 2026-03-24.
- 2026-03-10: Keep `tasks/COMPLETED.md` live as a compact index; require explicit `--include-archive` for archived task detail lookup.
- 2026-03-10: Treat `PROJECT_STATUS.md` as a pointer stub instead of a live milestone ledger.

## Risks / Foot-guns

- Shared workflow/tooling code assumes the old ledgers -> update CLI/tests/docs-freshness together.
- Live backlog rewrite could accidentally keep completed tasks -> generate from the archived full backlog and compact completion index.
- Archive access could silently leak back into default flows -> keep triage live-only and regression-test the explicit flag path.

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -k 'show or context_pack or search or triage or active' -q`
- `uv run --no-sync pytest tests/unit/core/test_docs_freshness.py -q`
- `uv run --no-sync python scripts/check_docs_freshness.py`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules: `src/horadus_cli/task_repo.py`, `src/horadus_cli/task_commands.py`, `src/core/docs_freshness.py`
