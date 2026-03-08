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
- Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
  needed workflow step yet, or when the CLI explicitly tells you a manual
  recovery step is required.
- If Horadus is insufficient or forces a fallback, record one structured
  friction entry via `horadus tasks record-friction`; do not log routine
  success cases or treat the friction log as required reading during normal
  execution.
- Fall back to repo files or legacy scripts only when the CLI does not expose
  the needed surface.

## Canonical commands

- Start preflight: `uv run --no-sync horadus tasks preflight`
- Canonical autonomous start: `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
- Context pack: `uv run --no-sync horadus tasks context-pack TASK-XXX`
- Fast iteration gate: `make agent-check`
- Canonical local gate: `uv run --no-sync horadus tasks local-gate --full`
- Lifecycle verifier: `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
- Finish: `uv run --no-sync horadus tasks finish TASK-XXX`
- Friction logging:
  `uv run --no-sync horadus tasks record-friction TASK-XXX --command-attempted "..." --fallback-used "..." --friction-type forced_fallback --note "..." --suggested-improvement "..."`
- Daily friction summary:
  `uv run --no-sync horadus tasks summarize-friction --date YYYY-MM-DD`
- Task list: `uv run --no-sync horadus tasks list-active --format json`
- Task record: `uv run --no-sync horadus tasks show TASK-XXX --format json`
- Task search: `uv run --no-sync horadus tasks search "query" --format json`
- Lower-level eligibility check: `uv run --no-sync horadus tasks eligibility TASK-XXX --format json`
- Lower-level branch start dry-run:
  `uv run --no-sync horadus tasks start TASK-XXX --name short-name --dry-run --format json`
- Triage bundle:
  `uv run --no-sync horadus triage collect --lookback-days 14 --format json`

## When to read more

- For command examples and output expectations, read
  `references/commands.md`.
