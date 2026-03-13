# TASK-325: Decompose `src/workers/tasks.py` Into Focused Internal Modules

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: In progress
- Planning Gates: Required — refactor touches a large worker surface, multiple task families, and contributor-facing module boundaries

## Goal (1-3 lines)

Break the worker task monolith into smaller internal modules by responsibility
while keeping the existing public Celery task surface and all runtime behavior
unchanged.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-325`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `src/workers/tasks.py`, `src/workers/celery_app.py`, `tests/unit/workers/test_tasks_additional.py`
- Preconditions/dependencies: current worker task names, decorator wiring, scheduling/dispatch semantics, and return payloads must remain stable

## Outputs

- Expected behavior/artifacts: thin `src/workers/tasks.py` facade plus focused internal modules for shared wrappers, collectors, processing coordination, retention cleanup, and replay/reporting/snapshot/decay logic
- Validation evidence: existing worker tests and relevant targeted checks pass without expectation changes

## Non-Goals

- Explicitly excluded work: feature changes, scheduling policy changes, queue/routing changes, task renames, or unrelated cleanup outside obsolete code introduced by the split

## Scope

- In scope: internal module extraction, compatibility-preserving re-exports, dead-file cleanup, and minimal doc/runbook updates if references become stale
- Out of scope: changing Celery configuration, modifying task payloads, or redesigning processing behavior

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep `src/workers/tasks.py` as the stable import surface and move implementation into internal worker modules
- Rejected simpler alternative: leave the monolith in place and add comments only; it does not improve navigability or test seams
- First integration proof: `tests/unit/workers/test_tasks_additional.py`
- Waivers: None

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Use a thin facade in `src/workers/tasks.py` so external worker imports and monkeypatch-friendly task names stay stable.

## Risks / Foot-guns

- Moving helpers can break tests that patch task-module globals -> keep stable exports in the facade and verify monkeypatch-heavy tests.
- Splitting retention and processing helpers can accidentally change import-time side effects -> keep decorator registration and signal hookup anchored in the facade.

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-325 --name split-worker-tasks`
- `pytest tests/unit/workers/test_tasks_additional.py -v`

## Notes / Links

- Spec:
- Relevant modules: `src/workers/tasks.py`, `src/workers/celery_app.py`, `tests/unit/workers/test_tasks_additional.py`
- Canonical example: `tasks/exec_plans/TASK-316.md`
