# TASK-311: Move Horadus CLI Into the Tooling Home and Isolate It from App Runtime Imports

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: In progress
- Planning Gates: Required — shared CLI/tooling ownership and import boundaries are changing

## Goal (1-3 lines)

Relocate Horadus CLI ownership from `src/horadus_cli/` into the tooling home
under `tools/horadus/python/`, keep `src/cli.py` thin, and remove direct
business-app imports from the shipped CLI package.

## Inputs

- Spec/backlog references:
  - `tasks/specs/311-move-horadus-cli-into-tools.md`
  - `tasks/BACKLOG.md` (`TASK-311`)
- Runtime/code touchpoints:
  - `src/cli.py`
  - `src/horadus_cli/`
  - `tools/horadus/python/horadus_workflow/`
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
  - Thin `src/cli.py` entrypoint
  - Explicit app-runtime adapter boundary for app-backed commands
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
  - Replace `src/horadus_cli/` implementation ownership with thin shims or deletion as appropriate
  - Update tests/docs/skill references to the new contract
- Out of scope:
  - New command families
  - Broader app architecture refactors unrelated to CLI ownership

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Keep the `horadus` entrypoint stable through `src/cli.py`, but move the
    importable CLI package and command owners into the existing tooling home.
- Rejected simpler alternative:
  - Leaving `src/horadus_cli/` as the stable home and only adjusting docs would
    preserve the ownership conflict the task is supposed to remove.
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
  keeping a stable `src/horadus_cli/` shell, because the user explicitly wants
  the CLI under `tools/` and isolated from business-app imports.
- 2026-03-12: Keep `src/cli.py` as the console entrypoint shim so the installed
  script contract stays stable while implementation ownership moves.

## Risks / Foot-guns

- In-repo imports and tests still anchored to `src.horadus_cli` -> update them
  in the same task and add import-boundary assertions for the new package.
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
  - `src/cli.py`
  - `src/horadus_cli/`
  - `tools/horadus/python/horadus_workflow/`
  - `tools/horadus/python/horadus_cli/`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
