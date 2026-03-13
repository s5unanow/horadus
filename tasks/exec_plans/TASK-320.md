# TASK-320: Tighten `ops_commands.py` Internal Seams After the Initial Split

## Status

- Owner: Codex
- Started: 2026-03-13
- Current state: In progress
- Planning Gates: Required — shared CLI internals and tests still constrain how far the follow-up cleanup can safely go

## Goal (1-3 lines)

Trim the lowest-value compatibility and helper indirection left by `TASK-319`
so the internal shape is cleaner, while preserving the exact external CLI
contract and existing runtime behavior.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-320`)
  - merged baseline from `TASK-319`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_cli/ops_commands.py`
  - `tools/horadus/python/horadus_cli/_ops_*.py`
  - `tests/horadus_cli/v2/test_ops_commands.py`
  - `tests/horadus_cli/v2/test_runtime_commands.py`
  - `tests/horadus_cli/v2/test_ops_rendering.py`
- Preconditions/dependencies:
  - preserve the current CLI surface and test-visible behavior
  - avoid undoing the useful separation between registration, smoke checks, and runtime bridge logic

## Outputs

- Expected behavior/artifacts:
  - smaller internal shape with at least one redundant layer removed
  - focused tests updated only where they currently lock in low-value private seams
- Validation evidence:
  - targeted ops CLI tests
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`
  - independent review before PR

## Non-Goals

- Explicitly excluded work:
  - CLI feature changes or public-surface cleanup
  - broad CLI architecture work outside the ops command group
  - test philosophy rewrite beyond what is needed to remove obvious low-value indirection

## Scope

- In scope:
  - fold or remove tiny helper modules/wrappers where they do not improve reasoning enough
  - keep the stronger module boundaries from `TASK-319` where they still pay for themselves
  - update tests if needed to target the cleaner internal seams
- Out of scope:
  - re-monolithizing parser registration into `ops_commands.py`
  - changing output copy or parser behavior

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - target the lowest-value indirection first (`_ops_results.py` and any equivalent façade-only wrappers) while preserving the more meaningful splits for registration, smoke checks, defaults, HTTP, and runtime bridge behavior
- Rejected simpler alternative:
  - leaving the current shape unchanged would keep avoidable wrapper noise even after we already identified it
- First integration proof:
  - the `TASK-319` test suite and repo gates already prove the behavior contract; preserve those and only adjust tests if they are locking in the redundant shape rather than real behavior
- Waivers:
  - none

## Plan (Keep Updated)

1. Preflight and branch start
2. Identify the lowest-value remaining indirection in the `TASK-319` result
3. Tighten the internals and update tests only where the old seam is purely incidental
4. Run targeted tests and repo gates
5. Review independently, then ship through the canonical PR/finish workflow

## Decisions (Timestamped)

- 2026-03-13: Treat the post-`TASK-319` tightening pass as a separate task because `TASK-319` is already merged and the follow-up should stay isolated in its own branch/PR.

## Risks / Foot-guns

- Over-collapsing the split can undo the maintainability gain from `TASK-319` -> keep registration, smoke, HTTP, defaults, and runtime bridge boundaries unless a boundary is clearly not paying off
- Existing tests may still depend on private helpers as patch targets -> move those seams carefully and keep behavior-based coverage intact
- Seemingly “tiny” wrappers can still encode compatibility assumptions -> verify with the existing targeted suite before broader gates

## Validation Commands

- `uv run --no-sync horadus tasks context-pack TASK-320`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_ops_commands.py tests/horadus_cli/v2/test_runtime_commands.py tests/horadus_cli/v2/test_ops_rendering.py -q`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
- `uv run --no-sync horadus tasks finish TASK-320`

## Notes / Links

- Relevant modules:
  - `tools/horadus/python/horadus_cli/ops_commands.py`
  - `tools/horadus/python/horadus_cli/_ops_registration.py`
  - `tools/horadus/python/horadus_cli/_ops_runtime_bridge.py`
