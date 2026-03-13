# TASK-323: Collapse repetitive finish refresh test scaffolding

## Problem Statement

`tests/horadus_cli/v2/task_finish/test_review_refresh.py` now carries a large
amount of repeated setup and monkeypatch boilerplate. The production behavior
is correct, but the test file is harder to scan than necessary.

## Inputs

- `AGENTS.md`
- `tasks/BACKLOG.md` (`TASK-323`)
- `tasks/CURRENT_SPRINT.md`
- `tests/horadus_cli/v2/task_finish/test_review_refresh.py`

## Outputs

- Smaller, clearer shared helpers for repeated refresh-test setup
- Parametrized/shared-dispatch coverage for repetitive failure-mapping cases
- No production behavior changes

## Non-Goals

- Changing production refresh logic
- Reducing assertion coverage or weakening failure-path coverage
- Refactoring unrelated finish tests

## Acceptance Criteria

- [ ] Repeated `FinishConfig(...)` setup is collapsed where it improves readability
- [ ] Repeated refresh failure-mapping cases use shared helpers and/or parametrization where safe
- [ ] Focused refresh tests still pass
- [ ] `uv run --no-sync horadus tasks local-gate --full` passes
