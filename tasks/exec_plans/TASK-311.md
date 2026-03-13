# TASK-311: Move Horadus CLI Into the Tooling Home and Isolate It from App Runtime Imports

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: In progress
- Planning Gates: Required — shared CLI/tooling ownership and import boundaries are changing

## Goal (1-3 lines)

Relocate Horadus CLI ownership from `src/` into the tooling home under
`tools/horadus/python/`, remove `src/cli.py`, `src/cli_runtime.py`, and
`src/horadus_cli/`, and keep direct business-app imports out of the shipped
CLI package.

## Inputs

- Spec/backlog references:
  - `tasks/specs/311-move-horadus-cli-into-tools.md`
  - `tasks/BACKLOG.md` (`TASK-311`)
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/`
  - `tools/horadus/python/horadus_app_cli_runtime.py`
  - `tools/horadus/python/horadus_cli/`
  - `tests/horadus_cli/`
  - `tests/workflow/`
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
  - `docs/ARCHITECTURE.md`
  - `ops/skills/horadus-cli/`
- Preconditions/dependencies:
  - Preserve the `horadus` CLI entrypoint
  - Keep repo-workflow behavior stable while changing ownership

## Outputs

- Expected behavior/artifacts:
  - Tooling-home CLI package with parser/result/command owners
  - Direct installed `horadus` entrypoint to the tooling-home CLI package
  - Explicit app-runtime adapter boundary for app-backed commands under `tools/`
  - Updated tests/docs/skill guidance
- Validation evidence:
  - Targeted CLI/workflow pytest coverage
  - Fast repo gate via `make agent-check`

## Non-Goals

- Explicitly excluded work:
  - Changing command semantics beyond the ownership move
  - Rewriting unrelated app runtime packages

## Scope

- In scope:
  - Move CLI implementation ownership into `tools/horadus/python/horadus_cli/`
  - Remove direct business-app imports from the tooling package
  - Delete `src/cli.py`, `src/cli_runtime.py`, and `src/horadus_cli/`
  - Update tests/docs/skill references to the new contract
- Out of scope:
  - New command families
  - Broader app architecture refactors unrelated to CLI ownership

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Point the installed `horadus` entrypoint directly at
    `tools/horadus/python/horadus_cli/app.py`, and move the app-runtime bridge
    to a sibling tooling module so `horadus_cli` itself stays isolated.
- Rejected simpler alternative:
  - Leaving any CLI ownership under `src/` would preserve the ownership
    conflict the task is supposed to remove.
- First integration proof:
  - `uv run --no-sync pytest tests/horadus_cli tests/workflow -q`
- Waivers:
  - None yet.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-12: Move the CLI into `tools/horadus/python/horadus_cli/` instead of
  keeping any stable `src/horadus_cli/` shell, because the user explicitly
  wants the CLI under `tools/` and isolated from business-app imports.
- 2026-03-13: Remove `src/cli.py` and move the runtime bridge to
  `tools/horadus/python/horadus_app_cli_runtime.py` so no Horadus CLI-owned
  module remains under `src/`.

## Risks / Foot-guns

- In-repo imports and tests still anchored to `src.horadus_cli` or `src.cli*`
  -> update them in the same task and add import-boundary assertions for the
  new package.
- App-backed ops commands currently import business modules lazily inside the
  CLI package -> replace them with an explicit adapter boundary that lives on
  the app/runtime side.
- Docs/skill guidance can drift from the new location -> update `AGENTS.md`,
  runbook, architecture, and skill references in the same change.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli tests/workflow -q`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_ops_commands.py -q`
- `make agent-check`

## Notes / Links

- Spec: `tasks/specs/311-move-horadus-cli-into-tools.md`
- Relevant modules:
  - `tools/horadus/python/horadus_app_cli_runtime.py`
  - `tools/horadus/python/horadus_workflow/`
  - `tools/horadus/python/horadus_cli/`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
