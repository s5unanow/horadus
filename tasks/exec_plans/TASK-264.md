# TASK-264: Enforce Horadus CLI, Skill, and Docs Drift Consistency

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Make the canonical Horadus task-workflow command set explicit in one shared
source, surface it in `context-pack`, and fail the repo-owned docs freshness
gate when the key agent-facing docs or skill drift away from that set.

## Scope

- In scope:
  - Shared canonical workflow-command definitions for task lifecycle guidance
  - `context-pack` output alignment to the canonical workflow-command set
  - Docs freshness drift checks for workflow docs and Horadus skill guidance
  - Tests for drift detection and updated context-pack output
- Out of scope:
  - New workflow commands beyond consistency/drift enforcement
  - Non-workflow documentation outside the agent/operator surfaces named in the task

## Plan (Keep Updated)

1. Preflight (branch, context, target surfaces)
2. Implement shared workflow-command source and drift checks
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-08: Extend the existing docs-freshness gate instead of adding a new
  standalone checker. (Keeps drift enforcement on the repo-owned path already
  used by local/CI validation.)
- 2026-03-08: Use one shared canonical command set for both docs drift checks
  and `context-pack` output. (Prevents the task from introducing another
  parallel source of truth.)

## Risks / Foot-guns

- Overly strict string matching can create noisy failures -> keep the canonical
  command set intentionally small and exact
- Docs can remain internally inconsistent if only one surface changes -> check
  every key agent-facing file in the same gate

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -k 'context_pack or workflow' -v`
- `uv run --no-sync pytest tests/unit/core/test_docs_freshness.py -k 'workflow' -v`
- `uv run --no-sync pytest tests/unit/test_cli.py -v`
- `uv run --no-sync pytest tests/unit/core/test_docs_freshness.py -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules:
  - `src/horadus_cli/task_commands.py`
  - `src/core/docs_freshness.py`
  - `tests/unit/test_cli.py`
  - `tests/unit/core/test_docs_freshness.py`
