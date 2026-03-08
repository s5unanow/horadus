# Horadus CLI Command Notes

## Repo workflow commands

- `uv run --no-sync horadus tasks preflight`
  - Enforces clean/synced `main`, required hooks, GitHub CLI availability, and no open task PRs unless explicitly bypassed.
- `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
  - Canonical autonomous task-start command.
  - Reuses eligibility checks and then creates the canonical
    `codex/task-XXX-short-name` branch.
- `uv run --no-sync horadus tasks context-pack TASK-XXX`
  - Returns backlog block, sprint lines, matching specs, likely code areas, and the canonical workflow/validation commands for the task.
- `make agent-check`
  - Fast inner-loop validation gate for lint, type-checking, and unit tests.
- `uv run --no-sync horadus tasks local-gate --full`
  - Canonical CI-parity local validation gate before push/PR.
- `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
  - Mechanical repo-policy verifier; success requires `local-main-synced`.
- `uv run --no-sync horadus tasks finish TASK-XXX`
  - Canonical task-completion lifecycle command.
- `uv run --no-sync horadus tasks record-friction TASK-XXX --command-attempted "..." --fallback-used "..." --friction-type forced_fallback --note "..." --suggested-improvement "..."`
  - Appends one structured workflow friction entry under the gitignored path
    `artifacts/agent/horadus-cli-feedback/entries.jsonl`.
  - Use only for real Horadus gaps or forced fallback, not routine success
    cases.
- `uv run --no-sync horadus tasks summarize-friction --date YYYY-MM-DD`
  - Writes the grouped daily friction report to
    `artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md`.
  - Keeps candidate follow-up work as human-review suggestions only; it does
    not create backlog tasks automatically.
- `uv run --no-sync horadus tasks list-active`
  - Returns active sprint tasks plus human blocker metadata.
- `uv run --no-sync horadus tasks show TASK-XXX`
  - Returns the backlog task record with status enrichment from sprint/completed ledgers.
- `uv run --no-sync horadus tasks search "query"`
  - Searches backlog tasks by title, description, files, and acceptance criteria.
- `uv run --no-sync horadus tasks eligibility TASK-XXX`
  - Checks sprint activeness, human-gated status, and task-start preflight.
- `uv run --no-sync horadus tasks start TASK-XXX --name short-name`
  - Lower-level branch creation command when eligibility was already handled.
  - Also creates the canonical `codex/task-XXX-short-name` branch.
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

- Do not skip prerequisite workflow steps such as preflight, guarded task
  start, or context collection just because the likely end state looks
  obvious.
- Prefer Horadus workflow commands over raw `git` / `gh` when the CLI covers
  the step because the CLI encodes sequencing, policy, and verification
  dependencies rather than just style.
- Keep using the workflow until prerequisite checks, required verification
  reruns, and completion verification succeed; do not stop at the first
  plausible success signal.
- Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
  needed workflow step yet, or when the CLI explicitly tells you a manual
  recovery step is required.
- Use `--format json` for agent consumption.
- Use text output when the command result is being read directly by a human in a terminal.
- Treat exit codes as part of the contract:
  - `0`: success
  - `2`: validation/policy failure
  - `3`: not found
  - `4`: environment/dependency failure
