# TASK-319: Decompose `ops_commands.py` Into Focused Internal Modules

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: In progress
- Planning Gates: Required — refactor touches a shared CLI surface, multiple command paths, and several test seams

## Goal (1-3 lines)

Split `tools/horadus/python/horadus_cli/ops_commands.py` by responsibility so
each command path is easier to trace and test, while preserving the exact
external CLI contract and runtime bridge behavior.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-319`)
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_cli/ops_commands.py`
  - `tools/horadus/python/horadus_cli/result.py`
  - `tools/horadus/python/horadus_app_cli_runtime.py`
  - `tests/horadus_cli/v2/test_ops_commands.py`
  - `tests/horadus_cli/v2/test_ops_rendering.py`
- Preconditions/dependencies:
  - Preserve the `TASK-310` / `TASK-311` runtime-bridge split
  - Keep CLI shell wiring and app runtime imports unchanged from the user’s perspective

## Outputs

- Expected behavior/artifacts:
  - focused internal modules under `tools/horadus/python/horadus_cli/`
  - `ops_commands.py` reduced to thin façade/orchestration
  - targeted tests proving behavior preservation across refactored seams
- Validation evidence:
  - targeted ops CLI test runs
  - repo fast gate and full local gate before finish
  - independent review pass before PR creation

## Non-Goals

- Explicitly excluded work:
  - CLI feature changes, new flags, or output copy edits
  - runtime bridge protocol changes
  - unrelated cleanup in other Horadus CLI command groups

## Scope

- In scope:
  - split parser wiring, runtime bridge helpers, smoke helpers, env/default resolution, and formatting helpers into smaller modules
  - keep imports/callers compatible with current CLI entry usage
  - update tests only where they need to follow the new internal ownership
- Out of scope:
  - changing command registration order without a behavior need
  - cross-cutting CLI reorganization beyond `ops_commands.py` ownership

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - introduce a small internal package or sibling modules owned by `ops_commands.py`, and re-export or delegate only the existing public helpers needed by tests/callers
- Rejected simpler alternative:
  - leaving the module monolithic and only adding comments would not create the test seams or traceability the task requires
- First integration proof:
  - existing `tests/horadus_cli/v2/test_ops_commands.py` and `tests/horadus_cli/v2/test_ops_rendering.py` already lock much of the external behavior; preserve them and add only narrow coverage for newly separated seams if a regression hole appears
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Map current `ops_commands.py` responsibilities and current test coverage
3. Implement focused internal modules with a thin façade
4. Run targeted tests, then fast/full gates
5. Review independently, address findings, then ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-13: Create an exec plan up front because the refactor is a shared CLI surface change with multiple files and test seams.

## Risks / Foot-guns

- Import-path drift can break test monkeypatch targets or command registration -> preserve stable names from `ops_commands.py` where tests/callers depend on them
- Small output-text changes can silently break CLI expectations -> keep formatting helpers behavior-identical and verify with existing rendering tests
- Runtime bridge payload normalization can regress app-backed commands -> isolate payload/result helpers and preserve current JSON/default rules

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-319`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_ops_commands.py tests/horadus_cli/v2/test_ops_rendering.py -q`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
- `uv run --no-sync horadus tasks finish TASK-319`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-319`)
- Relevant modules:
  - `tools/horadus/python/horadus_cli/ops_commands.py`
  - `tools/horadus/python/horadus_app_cli_runtime.py`
