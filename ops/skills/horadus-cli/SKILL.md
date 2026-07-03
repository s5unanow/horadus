---
name: horadus-cli
description: Use when operating the Horadus repo through task, sprint, triage, eval, or branch-start workflows; prefer the `horadus` CLI over ad hoc markdown parsing or one-off shell helpers when an equivalent command exists.
---

# Horadus CLI

Use this skill for repo workflow operations in this project. For command details,
read `references/commands.md`; for lifecycle policy and merge/review semantics,
read `AGENTS.md`.

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
- Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
  needed workflow step yet, or when the CLI explicitly tells you a manual
  recovery step is required.
- If a forced fallback is still required after those recovery attempts,
  record it with `horadus tasks record-friction`; do not log routine success
  cases or expected empty results.
- Fall back to repo files or legacy scripts only when the CLI does not expose
  the needed surface.

## Third-party docs lookup

Context7 may be used on demand as an agent/developer aid for current
third-party library and API documentation. It is not a Horadus runtime
dependency and must not replace local repo truth. Use `src/`, `alembic/`,
`tests/`, `docs/`, task specs, and `horadus tasks context-pack` as authoritative
for Horadus workflow, task lifecycle, probability math, migrations, and domain
contracts.

Prefer these high-value Context7 library IDs when a task needs current external
API details:

- `/openai/openai-python`
- `/fastapi/fastapi`
- `/pydantic/pydantic`
- `/pydantic/pydantic-settings`
- `/websites/sqlalchemy_en_20`
- `/websites/alembic_sqlalchemy`
- `/pgvector/pgvector-python`
- `/pgvector/pgvector`
- `/websites/celeryq_dev_en_stable`
- `/redis/redis-py`
- `/websites/python-httpx`
- `/open-telemetry/opentelemetry-python`
- `/open-telemetry/opentelemetry-python-contrib`
- `/websites/pytest_en_stable`
- `/websites/pytest-asyncio_readthedocs_io_en_stable`
- `/astral-sh/ruff`
- `/python/mypy`

Use these only when the task touches the relevant integration, release, or
tooling surface:

- `/encode/uvicorn`
- `/websites/magicstack_github_io_asyncpg_current`
- `/kurtmckee/feedparser`
- `/websites/lxml_de` or `/lxml/lxml`
- `/adbar/trafilatura` or `/websites/trafilatura_readthedocs_io_en`
- `/websites/telethon_dev_en_stable`
- `/websites/structlog_en_stable`
- `/prometheus/client_python`
- `/pre-commit/pre-commit.com`
- `/pycqa/bandit`
- `/ibm/detect-secrets`
- `/pypa/pip-audit`
- `/pypa/hatch`
- `/pypa/twine`
- `/yaml/pyyaml`
- `/websites/saurabh-kumar_python-dotenv`

Do not routinely seed Context7 lookups for `types-redis`, `types-pyyaml`,
`pytest-socket`, `build`, `hatchling`, or `twine` unless packaging, release, or
that exact tool is in scope.

## Command Surfaces

Root `horadus` command groups to check before falling back:

- `uv run --no-sync horadus trends status`
- `uv run --no-sync horadus dashboard export`
- `uv run --no-sync horadus eval benchmark`
- `uv run --no-sync horadus pipeline dry-run`
- `uv run --no-sync horadus agent smoke`
- `uv run --no-sync horadus doctor`
- `uv run --no-sync horadus tasks list-active`
- `uv run --no-sync horadus triage collect`

Core task lifecycle commands:

- Start preflight: `uv run --no-sync horadus tasks preflight`
- Dirty-main watchdog: `uv run --no-sync horadus tasks assert-safe-worktree`
- Canonical autonomous start: `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
- Context pack:
  `uv run --no-sync horadus tasks context-pack TASK-XXX --mode implement --format json`
- Close task ledgers in-branch:
  `uv run --no-sync horadus tasks close-ledgers TASK-XXX`
- Fast iteration gate: `make agent-check`
- Pre-push local review:
  `uv run --no-sync horadus tasks local-review --format json`
- Canonical local gate: `uv run --no-sync horadus tasks local-gate --full`
- Lifecycle verifier: `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
- Finish: `uv run --no-sync horadus tasks finish TASK-XXX`

Common follow-up and operations commands:

- Capture follow-up intake:
  `uv run --no-sync horadus tasks intake add --title "..." --note "..."`
- Promote intake only during deliberate grooming:
  `uv run --no-sync horadus tasks intake promote INTAKE-XXXX --priority ... --estimate ... --acceptance "..."`
- Automation lock health:
  `uv run --no-sync horadus tasks automation-lock check --automation-id <id>`
- Code-health eval:
  `uv run --no-sync horadus eval code-health`

Eval command reminders:

- Tier 1-only benchmark diagnostics:
  `uv run --no-sync horadus eval benchmark --tier-scope tier1`
- Tier 2-only benchmark diagnostics:
  `uv run --no-sync horadus eval benchmark --tier-scope tier2`
- Behavior evals: `uv run --no-sync horadus eval behavior`
- Taxonomy validation: `uv run --no-sync horadus eval validate-taxonomy`
- Regression intake: `uv run --no-sync horadus eval regression-intake`
- Vector benchmark: `uv run --no-sync horadus eval vector-benchmark`
- Embedding lineage: `uv run --no-sync horadus eval embedding-lineage`
- Source freshness: `uv run --no-sync horadus eval source-freshness`

## When to read more

- For command examples and output expectations, read `references/commands.md`
  or `docs/AGENT_RUNBOOK.md`.
- For canonical workflow policy and completion rules, read `AGENTS.md`.
- For high-risk cross-surface tasks (for example migrations, shared workflow
  tooling or config, shared math, or multi-surface mutation work), front-load
  adversarial review before the first push instead of discovering the whole bug
  set inside `horadus tasks finish`.
- If `horadus tasks context-pack TASK-XXX` recommends pre-push local review,
  follow that guidance. The default/env provider chain already falls through
  missing provider CLIs on PATH in repo order. If the first local-review run
  hits a provider-specific timeout, auth/config failure, or unreadable output
  and you still want local automation, rerun with `--allow-provider-fallback`;
  if the local-review path still remains unusable, request manual review early
  rather than waiting for the finish loop.
- Batch related fixes with updated tests before re-requesting review on a
  high-risk task; do not turn the same open bucket into a single-commit
  re-review loop.
- Provider selection for local review is: `--provider` override first, then
  `HORADUS_LOCAL_REVIEW_PROVIDER` from optional local-only `.env.harness`,
  then the repo default `claude`.
