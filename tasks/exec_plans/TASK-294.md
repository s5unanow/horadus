# TASK-294: Preserve Closed Task Bodies in Quarterly Archive Shards

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: In progress

## Goal (1-3 lines)

Add a first-class closed-task archive shard under `archive/closed_tasks/`,
preserve full task blocks there when tasks are closed, and make archive-aware
CLI lookup resolve those records only when explicitly requested.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-294`)
- Runtime/code touchpoints: `src/horadus_cli/task_repo.py`, `src/horadus_cli/task_commands.py`, `tests/horadus_cli/v1/test_cli.py`, `tests/unit/core/test_docs_freshness.py`
- Preconditions/dependencies: live backlog/current-sprint/completed ledgers already right-sized by `TASK-292`

## Outputs

- Expected behavior/artifacts:
  - quarterly archive shard format under `archive/closed_tasks/YYYY-QN.md`
  - task-ledger closure command that archives full task blocks and updates live ledgers
  - archive-aware `show`/`search`/`context-pack` support for quarterly shards
- Validation evidence:
  - unit tests for shard parsing and close-ledger flow
  - docs freshness and targeted CLI tests

## Non-Goals

- Explicitly excluded work:
  - pre-merge enforcement of closure state (`TASK-295`)
  - safe-start/preflight intake changes (`TASK-296`)
  - broad CLI fixture decoupling beyond what `TASK-294` needs (`TASK-293`)

## Scope

- In scope:
  - shard path computation
  - archive shard parser support
  - close-ledger writer behavior
  - docs/guidance for archive opt-in
- Out of scope:
  - changing task branch policy
  - merge/review gate behavior

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement archive shard parser + close-ledger writer
3. Validate targeted CLI/docs tests
4. Ship (commit, push, PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-10: Implement a dedicated task-ledger closure command before merge enforcement, so closure state can exist on the PR head and later be validated by `TASK-295`.

## Risks / Foot-guns

- Archive shard format drifts from backlog block parser -> reuse the same task block shape and separator rules.
- Close-ledger command mutates live ledgers incorrectly -> cover active/not-in-sprint/already-closed paths with tests before using enforcement in later tasks.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v1/test_cli.py -q`
- `uv run --no-sync pytest tests/unit/core/test_docs_freshness.py -q`
- `uv run --no-sync python scripts/check_docs_freshness.py`

## Notes / Links

- Spec: `tasks/BACKLOG.md#task-294-preserve-closed-task-bodies-in-quarterly-archive-shards`
- Relevant modules: `src/horadus_cli/task_repo.py`, `src/horadus_cli/task_commands.py`
