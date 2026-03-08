---
name: horadus-cli
description: Use when operating the Horadus repo through task, sprint, triage, or branch-start workflows; prefer the `horadus` CLI over ad hoc markdown parsing or one-off shell helpers when an equivalent command exists.
---

# Horadus CLI

Use this skill for repo workflow operations in this project.

## Default behavior

- Prefer `horadus` over direct `rg`/`awk`/markdown scraping when the CLI covers
  the workflow.
- Prefer `--format json` for agent use.
- Prefer `--dry-run` before any branch-creating command.
- Fall back to repo files or legacy scripts only when the CLI does not expose
  the needed surface.

## Canonical commands

- Task list: `uv run --no-sync horadus tasks list-active --format json`
- Task record: `uv run --no-sync horadus tasks show TASK-XXX --format json`
- Task search: `uv run --no-sync horadus tasks search "query" --format json`
- Context pack: `uv run --no-sync horadus tasks context-pack TASK-XXX --format json`
- Start preflight: `uv run --no-sync horadus tasks preflight --format json`
- Canonical autonomous start dry-run:
  `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name --dry-run --format json`
- Lower-level eligibility check:
  `uv run --no-sync horadus tasks eligibility TASK-XXX --format json`
- Lower-level branch start dry-run:
  `uv run --no-sync horadus tasks start TASK-XXX --name short-name --dry-run --format json`
- Local gate: `uv run --no-sync horadus tasks local-gate --full --format json`
- Lifecycle verifier: `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict --format json`
- Finish: `uv run --no-sync horadus tasks finish TASK-XXX --format json`
- Triage bundle:
  `uv run --no-sync horadus triage collect --lookback-days 14 --format json`

## When to read more

- For command examples and output expectations, read
  `references/commands.md`.
