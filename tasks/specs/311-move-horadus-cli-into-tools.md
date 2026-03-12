# TASK-311: Move Horadus CLI Into the Tooling Home and Isolate It from App Runtime Imports

## Problem Statement

The Horadus CLI still lives under `src/horadus_cli/`, which mixes repo
workflow tooling with application-owned runtime code. That layout now conflicts
with the repo's tooling-home direction under `tools/horadus/python/` and keeps
the CLI coupled to business modules through `ops_commands.py`.

The result is architectural drift in three places: packaging still treats the
CLI as part of app runtime ownership, tests and docs still describe
`src/horadus_cli/` as the stable home, and the CLI package can import app
logic directly. That makes the CLI harder to reason about as a self-contained
tooling surface.

## Inputs

- `AGENTS.md`
- `tasks/CURRENT_SPRINT.md`
- `tasks/BACKLOG.md`
- `docs/ARCHITECTURE.md`
- `docs/AGENT_RUNBOOK.md`
- `src/cli.py`
- `src/horadus_cli/`
- `tools/horadus/python/horadus_workflow/`
- `tests/horadus_cli/`
- `tests/workflow/`
- `ops/skills/horadus-cli/`

## Outputs

- A tooling-home Horadus CLI package under `tools/horadus/python/horadus_cli/`
  that owns parser wiring, command handlers, and result rendering
- A thin `src/cli.py` entrypoint that delegates to the tooling package
- An explicit app-runtime adapter boundary for commands that need app-owned
  behavior, without direct business-app imports inside the CLI package
- Updated tests, docs, runbook entries, and repo skill guidance for the new
  ownership boundary and import contract

## Non-Goals

- Reworking the semantics of existing task, triage, review-gate, or app
  commands beyond what the move requires
- Redesigning the public command vocabulary
- Moving unrelated application runtime packages out of `src/`

**Planning Gates**: Required — shared workflow/tooling ownership is moving and
the task changes packaging, imports, tests, and agent guidance across the repo.

## Phase -1 / Pre-Implementation Gates

- `Simplicity Gate`: Extend the existing tooling home under
  `tools/horadus/python/` instead of introducing a second tooling root or a new
  command runner stack.
- `Anti-Abstraction Gate`: Add only the minimum adapter needed to let CLI
  commands invoke app-owned behavior without importing business modules into the
  tooling package.
- `Integration-First Gate`:
  - Validation target: `uv run --no-sync horadus ...` still behaves the same
    from the repo root after the move.
  - Exercises: parser tests, workflow tests, CLI import-boundary tests, and
    app-command adapter tests.
- `Determinism Gate`: Triggered — path resolution, subprocess protocol, and
  parser wiring must stay deterministic.
- `LLM Budget/Safety Gate`: Not applicable — no LLM behavior changes.
- `Observability Gate`: Not applicable — no new runtime telemetry surface is
  expected from this packaging move.

## Shared Workflow/Policy Change Checklist

- Callers that depend on the current CLI ownership/import surface:
  - `src/cli.py`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/horadus_cli/v2/test_ops_commands.py`
  - `tests/horadus_cli/shell/test_cli_versioning.py`
  - `tests/workflow/test_task_workflow.py`
  - `scripts` and docs that name `src/horadus_cli/`
- Unaffected-caller regression target:
  - Keep workflow-owner tests under `tests/workflow/` green while moving the
    CLI package so repo-workflow owners do not silently drift.

## Acceptance Criteria

- [ ] Runtime CLI ownership moves to `tools/horadus/python/horadus_cli/`
- [ ] `src/cli.py` remains a thin entrypoint only; `src/horadus_cli/` no longer
  owns live CLI implementation logic
- [ ] The tooling-home CLI package does not directly import business-app logic
  from `src/core`, `src/storage`, `src/processing`, `src/eval`, or similar
- [ ] App-backed commands use an explicit adapter boundary that keeps app-owned
  imports on the runtime side
- [ ] Tests and docs enforce the new ownership and import contract

## Validation

- `uv run --no-sync pytest tests/horadus_cli tests/workflow -q`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_ops_commands.py -q`
- `make agent-check`
