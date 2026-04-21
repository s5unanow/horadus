---
name: ship-it
description: Use when the user wants the agent to take an active Horadus sprint task from planning through canonical completion; infer the target from the current task branch or current sprint when the user does not name a task, then drive the full Horadus workflow instead of stopping at implementation or a local commit.
---

# Ship It

Use this skill when the user wants full task delivery in this repo.

This skill is not a generic coding shortcut. It is a completion contract for
Horadus task work:

- completion means `uv run --no-sync horadus tasks finish TASK-XXX` succeeds
- final verification means
  `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` reports success
- if the task cannot reach that state, report the exact blocker and the furthest
  completed lifecycle step

## Required repo context

Read these before acting:

- `AGENTS.md`
- `tasks/CURRENT_SPRINT.md`
- `ops/skills/horadus-cli/SKILL.md`

Prefer the Horadus CLI over ad hoc markdown parsing whenever the CLI covers the
step.

## Target selection

Resolve the task in this order:

1. If the user names `TASK-XXX`, use it.
2. If the current branch already matches `codex/task-XXX-*`, continue that task
   instead of selecting a new one.
3. Otherwise run `uv run --no-sync horadus tasks list-active --format json` and
   pick the first active sprint task with `requires_human=false`.

Never autonomously start a `[REQUIRES_HUMAN]` task.

Before branch creation or continuation, verify eligibility with:

```bash
uv run --no-sync horadus tasks eligibility TASK-XXX --format json
```

If eligibility fails, stop and report the CLI blocker.

## Canonical flow

Run the task through this sequence:

1. `uv run --no-sync horadus tasks context-pack TASK-XXX --mode implement --format json`
2. If planning gates are required and the authoritative artifact is missing,
   create the missing spec or exec plan before implementation.
3. If not already on the correct task branch, start with
   `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`.
4. Implement the task against runtime truth in `src/`, `alembic/`, `tests/`,
   and any task-owned workflow/docs files.
5. Run targeted validation from the context pack plus baseline local gates.
6. If the context pack recommends pre-push local review, run
   `uv run --no-sync horadus tasks local-review --format json` before push or
   re-review.
7. Update all required docs, sprint/task ledgers, and planning artifacts in the
   same branch.
8. Run `uv run --no-sync horadus tasks local-gate --full`.
9. Run `uv run --no-sync horadus tasks finish TASK-XXX`.
10. Run `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`.

Do not stop after code changes, local tests, or a local commit unless the user
explicitly asks for a checkpoint.

## Implementation rules

- Use the validation commands surfaced by `context-pack`; shared helpers and
  shared math require explicit `make typecheck`.
- When the task changes workflow, review, policy, or operator-facing behavior,
  update the matching docs in the same branch.
- For hotspot-touch tasks or any task where planning gates are required, record
  the required planning markers before coding.
- Keep unrelated follow-up work out of the task branch; capture it with the
  intake flow when needed.
- Prefer raw `git` or `gh` only when the Horadus CLI does not expose the step
  or the CLI explicitly instructs manual recovery.

## Stop conditions

The task is done only when one of these is true:

- `horadus tasks lifecycle TASK-XXX --strict` succeeds with the repo back on
  synced `main`
- a concrete external blocker remains after the canonical workflow has been
  pushed as far as possible

If blocked, report:

- target task id
- current branch and PR state if any
- exact failing command
- exact blocker
- furthest completed lifecycle step

Do not report vague partial completion such as "implemented locally" or
"tests pass" as task completion.
