# Horadus CLI Command Notes

## Repo workflow commands

- `horadus tasks list-active`
  - Returns active sprint tasks plus human blocker metadata.
- `horadus tasks show TASK-XXX`
  - Returns the backlog task record with status enrichment from sprint/completed ledgers.
- `horadus tasks search "query"`
  - Searches backlog tasks by title, description, files, and acceptance criteria.
- `horadus tasks context-pack TASK-XXX`
  - Returns backlog block, sprint lines, matching specs, likely code areas, and suggested validation commands.
- `horadus tasks preflight`
  - Enforces clean/synced `main`, required hooks, GitHub CLI availability, and no open task PRs unless explicitly bypassed.
- `horadus tasks eligibility TASK-XXX`
  - Checks sprint activeness, human-gated status, and task-start preflight.
- `horadus tasks start TASK-XXX --name short-name`
  - Creates the canonical `codex/task-XXX-short-name` branch.
  - Use `--dry-run` before performing the actual branch switch.

## Triage commands

- `horadus triage collect`
  - Produces a structured bundle for weekly backlog triage and related automation.
  - Supports repeatable filters:
    - `--keyword`
    - `--path`
    - `--proposal-id`
    - `--lookback-days`

## Output guidance

- Use `--format json` for agent consumption.
- Use text output when the command result is being read directly by a human in a terminal.
- Treat exit codes as part of the contract:
  - `0`: success
  - `2`: validation/policy failure
  - `3`: not found
  - `4`: environment/dependency failure
