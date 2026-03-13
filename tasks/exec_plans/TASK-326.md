# TASK-326: Let `horadus tasks finish` Bootstrap Missing PRs Canonically

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: In progress
- Planning Gates: Required — shared workflow behavior, policy/docs alignment, and compatibility-heavy finish tests

## Goal (1-3 lines)

Extend `horadus tasks finish` so it owns the missing-PR bootstrap path by
pushing the task branch when needed, creating the canonical PR when missing,
and continuing through the existing finish lifecycle without manual `gh`
fallback in the normal case.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-326`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/task_workflow_finish/`, `tools/horadus/python/horadus_cli/task_workflow_core.py`, `tests/horadus_cli/v2/task_finish/`
- Preconditions/dependencies: preserve current review-gate/merge semantics, PR scope guard rules, lifecycle recovery from `main`, and canonical docs/policy surfaces

## Outputs

- Expected behavior/artifacts: finish-owned push/PR-create bootstrap with branch-centric dedupe, compatible dry-run reporting, updated workflow policy/docs/skill references, and regression coverage
- Validation evidence: targeted finish tests, unaffected shared-caller regression, `make agent-check`, and canonical local gate if feasible

## Non-Goals

- Explicitly excluded work: redesigning review comment semantics, changing merge policy, adding new finish flags, or broadening PR body/template behavior beyond the canonical metadata line

## Scope

- In scope: finish bootstrap helpers, orchestrator changes, compatibility exports if needed, tests, and doc/policy/skill updates tied to the new behavior
- Out of scope: changing lifecycle task-id PR discovery semantics for unrelated callers, changing review timeout policy, or adding general-purpose GitHub timeline/comment browsing

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep `finish` as the canonical lifecycle orchestrator and add a focused bootstrap helper for missing remote branch / missing PR handling
- Rejected simpler alternative: keep the manual recovery and only update docs; it preserves a known workflow gap and keeps forcing fallback in the normal path
- First integration proof: `tests/horadus_cli/v2/task_finish/test_finish_data.py`
- Waivers: None

## Plan (Keep Updated)

1. Preflight (branch, context, targeted tests)
2. Implement finish bootstrap + dedupe
3. Validate behavior and docs/policy alignment
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Keep PR bootstrap dedupe branch-centric; `Primary-Task` search remains a recovery surface, not the primary create/attach key.

## Risks / Foot-guns

- Auto-creating PRs can create duplicates under reruns/races -> require branch-based lookup before create and immediate re-query after create failures.
- Doc/policy drift can silently reintroduce manual-fallback guidance -> update the canonical workflow owners and rerun docs freshness/local gates.
- Compatibility tests monkeypatch finish-module exports heavily -> preserve or intentionally re-export new helpers through the compat module.

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-326 --name finish-pr-bootstrap`
- `uv run --no-sync pytest tests/horadus_cli/v2/task_finish/ -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Relevant modules: `tools/horadus/python/horadus_workflow/task_workflow_finish/orchestrator.py`, `tools/horadus/python/horadus_workflow/task_workflow_finish/context.py`, `tools/horadus/python/horadus_cli/task_workflow_core.py`
- Related prior finish work: `TASK-307`, `TASK-309`, `TASK-322`
