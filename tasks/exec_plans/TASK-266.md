# TASK-266: Add Daily Horadus Friction Summary Automation

## Status

- Owner: Codex
- Started: 2026-03-08
- Current state: Validation complete; ready to ship

## Goal (1-3 lines)

Add a canonical Horadus workflow that turns structured friction log entries into
a compact daily summary, then wire that workflow into the repo-owned automation
desired state that syncs into local `$CODEX_HOME/automations/`.

## Scope

- In scope:
  - Add a `horadus tasks` command for daily friction summaries
  - Version the daily automation desired state under `ops/automations/`
  - Add/update operator-facing docs for report location and triage rules
  - Cover the summary behavior with unit tests
- Out of scope:
  - Automatic backlog task creation
  - Changes to unrelated automation flows

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement canonical friction-summary command and report generation
3. Add repo-owned automation spec/instructions and doc updates
4. Validate
5. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-08: Use a canonical `horadus tasks summarize-friction` command as the
  automation surface so the report logic is testable in-repo and not duplicated
  in automation prompts.

## Risks / Foot-guns

- Daily reports could become noisy if they mirror raw JSONL entries ->
  summarize by grouped patterns and candidate improvements instead of dumping
  verbatim rows.
- Repo-owned automation specs must remain the source of truth ->
  update `ops/automations/ids.txt` and validate with the existing sync tooling.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v1/test_cli.py -k 'summarize_friction or summarize-friction' -v`
- `uv run --no-sync pytest tests/unit/scripts/test_sync_automations.py -v`
- `uv run --no-sync horadus tasks summarize-friction --date 2026-03-08 --dry-run --format json`
- `make automations-apply`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-266`)
- Relevant modules: `src/horadus_cli/task_commands.py`, `scripts/sync_automations.py`, `ops/automations/`
