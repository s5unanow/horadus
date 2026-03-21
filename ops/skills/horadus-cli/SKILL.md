---
name: horadus-cli
description: Use when operating the Horadus repo through task, sprint, triage, or branch-start workflows; prefer the `horadus` CLI over ad hoc markdown parsing or one-off shell helpers when an equivalent command exists.
---

# Horadus CLI

Use this skill for repo workflow operations in this project.

Implementation note:
- Canonical CLI ownership lives under `tools/horadus/python/horadus_cli/`.
- The installed `horadus` entrypoint points directly at the tooling package.
- App-backed commands cross `tools/horadus/python/horadus_app_cli_runtime.py`;
  the tooling package should not import business-app modules directly.

## Default behavior

- Prefer `horadus` over direct `rg`/`awk`/markdown scraping when the CLI covers
  the workflow.
- Prefer `--format json` for agent use.
- Prefer `--dry-run` before any branch-creating command.
- Read `AGENTS.md` for canonical workflow policy, completion rules, and merge/review semantics.
- Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
  needed workflow step yet, or when the CLI explicitly tells you a manual
  recovery step is required.
- If a forced fallback is still required after those recovery attempts,
  record it with `horadus tasks record-friction`; do not log routine success
  cases or expected empty results.
- Fall back to repo files or legacy scripts only when the CLI does not expose
  the needed surface.

## Canonical commands

- Start preflight: `uv run --no-sync horadus tasks preflight`
- Canonical autonomous start: `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
- Context pack: `uv run --no-sync horadus tasks context-pack TASK-XXX`
- Fast iteration gate: `make agent-check`
- Pre-push local review:
  `uv run --no-sync horadus tasks local-review --format json`
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

- For high-risk cross-surface tasks (for example migrations, shared workflow
  tooling or config, shared math, or multi-surface mutation work), front-load
  adversarial review before the first push instead of discovering the whole bug
  set inside `horadus tasks finish`.
- If `horadus tasks context-pack TASK-XXX` recommends pre-push local review,
  follow that guidance. When the selected provider is unavailable and local
  automation is still desired, rerun with `--allow-provider-fallback`; if the
  local-review path remains unusable, request manual review early rather than
  waiting for the finish loop.
- Batch related fixes with updated tests before re-requesting review on a
  high-risk task; do not turn the same open bucket into a single-commit
  re-review loop.
- Provider selection for local review is: `--provider` override first, then
  `HORADUS_LOCAL_REVIEW_PROVIDER` from optional local-only `.env.harness`,
  then the repo default `claude`.
- For canonical workflow policy and completion rules, read `AGENTS.md`.
- For command examples and output expectations, read `references/commands.md`
  or `docs/AGENT_RUNBOOK.md`.
