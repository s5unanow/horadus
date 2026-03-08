# TASK-263: Route Repo Workflow Automation Through Horadus CLI and Skill

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Make the Horadus CLI the canonical task-workflow surface for autonomous start
operations, then align wrappers, docs, and the repo-owned skill to that single
entrypoint.

## Scope

- In scope:
  - Add a guarded CLI task-start entrypoint for agent workflow use
  - Keep Make targets as compatibility wrappers where they still exist
  - Update agent-facing docs and the Horadus skill to prefer the canonical CLI
  - Add tests for the new CLI entrypoint and wrapper contract
- Out of scope:
  - Changing non-task repo workflows outside practical Horadus CLI coverage
  - Reworking merge/finish behavior already handled by earlier tasks

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-08: Add a first-class guarded start command instead of documenting a
  Make wrapper as canonical. (Matches repo policy that Horadus should be the
  workflow surface whenever an equivalent command exists.)
- 2026-03-08: Keep `horadus tasks start` as the lower-level branch-creation
  primitive and layer `horadus tasks safe-start` above it. (Avoids replacing an
  existing useful primitive while giving agents one canonical autonomous entry
  point.)

## Risks / Foot-guns

- Docs can drift if only one surface is updated -> update AGENTS, README,
  runbook, and skill in the same task
- Wrapper behavior can diverge from CLI behavior -> make wrapper delegate to
  the new CLI entrypoint

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -k 'safe_start or start' -v`
- `uv run --no-sync pytest tests/unit/test_cli.py -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules:
  - `src/horadus_cli/task_commands.py`
  - `ops/skills/horadus-cli/SKILL.md`
  - `docs/AGENT_RUNBOOK.md`
  - `README.md`
  - `AGENTS.md`
