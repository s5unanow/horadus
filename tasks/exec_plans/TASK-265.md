# TASK-265: Add Structured Horadus CLI Friction Logging

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Add a low-noise, structured way to record real Horadus workflow friction or
forced fallback without mixing that operational feedback into versioned planning
or product source-of-truth records.

## Scope

- In scope:
  - Structured friction-log append helper/CLI entrypoint
  - Gitignored storage under `artifacts/agent/horadus-cli-feedback/`
  - Agent-facing guidance for when to record friction and when not to
  - Unit coverage for append/validation behavior
- Out of scope:
  - Reading or summarizing the friction log during routine task execution
  - Product/runtime telemetry unrelated to agent workflow friction

## Plan (Keep Updated)

1. Preflight (branch, context, artifact path, CLI surface)
2. Implement friction logging command and guidance
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-08: Use gitignored JSONL under `artifacts/agent/horadus-cli-feedback/`
  for append-only workflow friction capture. (Keeps entries structured,
  local/non-source-of-truth, and easy to append without extra dependencies.)
- 2026-03-08: Add a dedicated CLI append path instead of asking agents to edit
  artifact files manually. (Keeps the friction format structured and testable
  while preserving a low-friction operator workflow.)

## Risks / Foot-guns

- Friction logging can become noisy if treated like a routine diary -> document
  that entries are for real gaps or forced fallback only
- Feedback can leak into source-of-truth planning data -> keep it under ignored
  artifacts and avoid references from backlog/sprint status paths

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -k 'record_friction or friction' -v`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none
- Relevant modules:
  - `src/horadus_cli/task_commands.py`
  - `docs/AGENT_RUNBOOK.md`
  - `AGENTS.md`
  - `ops/skills/horadus-cli/SKILL.md`
  - `tests/unit/test_cli.py`
