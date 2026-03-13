# TASK-324: Decompose `task_workflow_preflight.py` Into Focused Internal Modules

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: In progress
- Planning Gates: Required — refactor spans multiple workflow modules and test seams

## Goal (1-3 lines)

Refactor `task_workflow_preflight.py` into smaller internal modules that each
own one concern, while keeping the public module surface, CLI behavior, and
existing test expectations unchanged.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-324`), `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/task_workflow_preflight.py`, `tools/horadus/python/horadus_cli/task_workflow_core.py`
- Preconditions/dependencies: guarded task-start flow, existing preflight/start/safe-start tests

## Outputs

- Expected behavior/artifacts: thin compatibility facade plus focused internal modules for intake analysis, ownership detection, repo checks, eligibility, and start orchestration
- Validation evidence: targeted CLI/workflow tests for preflight/start/safe-start pass without expectation changes

## Non-Goals

- Explicitly excluded work: policy changes, CLI output changes, unrelated cleanup, or broader workflow rewrites

## Scope

- In scope: internal module split, compatibility exports, redundant-file cleanup, minimal doc touch-up if contributor guidance needs it
- Out of scope: changing task-start policy, changing hook/open-PR semantics, or redesigning the CLI shell

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep `task_workflow_preflight` as the external facade and move logic behind it
- Rejected simpler alternative: keep the monolith and only add comments; it does not improve testable ownership seams
- First integration proof: `tests/horadus_cli/v2/test_task_preflight.py`
- Waivers: None

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Use a compatibility facade/package so existing imports and monkeypatch-based tests remain stable.

## Risks / Foot-guns

- Compatibility shims may stop forwarding monkeypatches -> mirror the existing compat-module pattern and keep the same exported names.
- Moving helper functions can accidentally change output ordering -> preserve the current decision order and verify with targeted tests.

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-324 --name split-preflight`
- `pytest tests/horadus_cli/v2/test_task_preflight.py -v`

## Notes / Links

- Spec:
- Relevant modules: `tools/horadus/python/horadus_workflow/task_workflow_preflight.py`, `tools/horadus/python/horadus_cli/task_workflow_core.py`
- Canonical example: `tasks/exec_plans/TASK-316.md`
