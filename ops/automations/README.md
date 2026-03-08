# Repo-Owned Codex Automations (Desired State)

Codex automations live locally under `$CODEX_HOME/automations/<id>/automation.toml`
(typically `~/.codex/automations/...`) and are not versioned by default.

This directory stores the repo’s **desired state** for *repo-relevant* automations
so prompts/schedules are reviewable and stable over time.

## What Is Versioned

- `ops/automations/specs/<id>.toml`: stable automation fields (prompt, schedule, cwds, etc.)
- `ops/automations/ids.txt`: allowlist of automation IDs considered part of this repo
- Example repo-owned ops automation:
  - `daily-horadus-friction-summary` writes daily grouped friction reports to
    `artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md`

Volatile local fields like `created_at` / `updated_at` are intentionally **not**
tracked to avoid git churn.

## Sync Workflow

- Export local Codex automations into repo specs:
  - `make automations-export`
- Apply repo specs back into local Codex automation TOMLs:
  - `make automations-apply`

The sync tool only operates on IDs in `ops/automations/ids.txt`.
Apply repo specs after updating desired state so local
`$CODEX_HOME/automations/<id>/automation.toml` stays in sync with git-tracked
specs.
