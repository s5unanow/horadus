# Horadus CLI Command Notes

## Repo workflow commands

Implementation note:
- CLI ownership lives under `tools/horadus/python/horadus_cli/`.
- The installed `horadus` entrypoint points directly at the tooling package.
- App-backed commands cross `tools/horadus/python/horadus_app_cli_runtime.py`
  instead of importing business-app modules into the tooling package.

- For canonical workflow policy, blocker handling, and fallback rules, read
  `AGENTS.md`.
- Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
  needed workflow step yet, or when the CLI explicitly tells you a manual
  recovery step is required.

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
  - If the PR head changes during or between finish runs, the CLI refreshes
    stale older-head review state, owns any fresh re-review request for the
    new head, and starts a fresh review window; the agent should address
    feedback, push changes, and rerun `horadus tasks finish TASK-XXX`.
  - For merge/review policy and timeout semantics, read `AGENTS.md`.
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
