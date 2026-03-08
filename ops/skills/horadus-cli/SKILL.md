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
- Do not skip prerequisite workflow steps such as preflight, guarded task
  start, or context collection just because the likely end state looks
  obvious.
- Prefer Horadus workflow commands over raw `git` / `gh` when the CLI covers
  the step because the CLI encodes sequencing, policy, and verification
  dependencies rather than just style.
- Keep using the workflow until prerequisite checks, required verification
  reruns, and completion verification succeed; do not stop at the first
  plausible success signal.
- Treat an empty, partial, or suspiciously narrow workflow result as a
  retrieval problem first when the missing data likely exists.
- Before concluding that no result exists, try one or two sensible recovery
  steps such as broader Horadus queries, alternate filters, or the documented
  manual recovery path.
- If a forced fallback is still required after those recovery attempts,
  record it with `horadus tasks record-friction`; do not log routine success
  cases or expected empty results.
- Treat repo-facing work as incomplete until requested deliverables, required
  repo updates, and required verification/gate runs are finished or
  explicitly reported blocked.
- Implementation, required tests/gates, and required task/doc/status updates
  remain part of the same task unless they are explicitly blocked.
- If a task is blocked, report the exact missing item, the blocker causing it,
  and the furthest completed lifecycle step rather than a vague
  partial-completion claim.
- Do not claim a task is complete, done, or finished until
  `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` passes or
  `horadus tasks finish TASK-XXX` completes successfully.
- The default review-gate timeout for `horadus tasks finish` is 600 seconds
  (10 minutes). Agents must not override it unless a human explicitly
  requested a different timeout.
- Do not proactively suggest changing the `horadus tasks finish` review
  timeout; wait the canonical 10-minute window unless the human explicitly
  asked otherwise.
- A `THUMBS_UP` reaction from the configured reviewer on the PR summary
  counts as a positive review-gate signal, but the gate still waits the full
  timeout window and still blocks actionable current-head review comments.
- Local commits, local tests, and a clean working tree are checkpoints, not
  completion.
- Do not stop at a local commit boundary unless the user explicitly asked for
  a checkpoint.
- Resolve locally solvable environment blockers before reporting blocked.
- If Horadus is insufficient or forces a fallback after sensible recovery
  attempts, record one structured friction entry via
  `horadus tasks record-friction`; do not log routine success cases,
  expected empty results, or treat the friction log as required reading
  during normal execution.
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
