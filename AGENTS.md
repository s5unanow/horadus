# Agent Instructions (Canonical)

This repo is a hobby “geopolitical intelligence” backend (not enterprise scale; expect **≤ 20 trends**). Despite being personal, it aims to be **mature and production-shaped**, adhering to **enterprise best practices where reasonable** (tests, migrations, type safety, observability, safe defaults, cost controls) without premature over-engineering.

## What This Project Is

- Headless backend that ingests public news/posts, clusters them into **events**, and updates **trend probabilities** using **log-odds**.
- Key principle: **LLM extracts structured signals; deterministic code computes probability deltas**.

## Where To Look First (Fast Orientation)

1. `tasks/CURRENT_SPRINT.md` — active execution queue (authoritative for in-progress work)
2. `tasks/BACKLOG.md` — canonical open task specifications and acceptance criteria (triage/planning; not required for most execution)
3. `tasks/COMPLETED.md` — compact completion index
4. `docs/ARCHITECTURE.md` — system design and runtime flow
5. `docs/DATA_MODEL.md` — schema and entity definitions
6. `docs/AGENT_RUNBOOK.md` — canonical day-to-day command index

## Canonical Source-of-Truth Hierarchy

When guidance conflicts, resolve it in this order.

Execution precedence:
1. Runtime truth: `src/`, `alembic/`, and `tests/`
2. Active execution plan: `tasks/CURRENT_SPRINT.md`
3. Task scope records: `tasks/BACKLOG.md` and `tasks/COMPLETED.md`
4. Design/ops docs: `docs/`
5. Pointer-only status surface: `PROJECT_STATUS.md`
6. Historical snapshots: `archive/`, `archive/closed_tasks/`, and `docs/POTENTIAL_ISSUES.md` (non-authoritative; do not read unless explicitly requested)

Status precedence:
1. `tasks/CURRENT_SPRINT.md` for what is active now
2. `tasks/COMPLETED.md` for what is done
3. `tasks/BACKLOG.md` for open task definitions
4. `PROJECT_STATUS.md` only as a pointer to archived history

## Repo Map

- `src/api/` — FastAPI app and routes
- `src/core/` — domain logic (trend math, config)
- `src/storage/` — DB engine + SQLAlchemy models
- `src/ingestion/` — collectors (may be stubbed early)
- `src/processing/` — LLM + clustering + pipeline (may be stubbed early)
- `src/workers/` — async/background workers (may be stubbed early)
- `tools/horadus/python/horadus_workflow/` — repo workflow/tooling ownership (task/PR/docs governance)
- `config/` — YAML configuration (`trends/`, `sources/`)
- `ai/` — LLM assets (prompts, evaluation data, benchmark results)
- `docs/` — architecture, glossary, ADRs (`docs/adr/`)
- `tasks/` — backlog, sprint, and detailed specs (`tasks/specs/`)
- `tests/` — unit/integration tests

## Working Agreements (Personal-Scale)

- Prefer **simple, debuggable** solutions over distributed complexity.
- Optimize for: **bounded cost**, **traceability**, and **iterability**.
- Keep **production-like discipline**: clear module boundaries, migrations, idempotency, retries/backoff, structured logs, and tests for core logic.
- Avoid adding infrastructure unless it enables a concrete next milestone.

## Workflow (How To Work In This Repo)

Before starting work:
- Read `tasks/CURRENT_SPRINT.md` and any relevant `tasks/specs/*.md`.
- Skim `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` for context.
- Run tests relevant to your change (at minimum unit tests).

Execution context policy (keep it small):
- For implementation work, prefer `tasks/CURRENT_SPRINT.md` plus the specific task spec it references; avoid reading all of `tasks/BACKLOG.md` unless you are doing triage/planning.
- Do not read `archive/` or `archive/closed_tasks/` during normal implementation flow unless the user explicitly asks for historical context.
- For tasks with high complexity (estimate >2 hours, touches >5 files, involves migrations, LLM/pipeline changes, or probability math/ops guardrails), maintain a living execution plan at `tasks/exec_plans/TASK-XXX.md` using `tasks/exec_plans/TEMPLATE.md`.
- Keep backlog entries concise and task-shaped; detailed implementation boundaries, migration strategy, risks, and validation belong in the exec plan when one exists.
- Apply these guardrails only when changing shared workflow helpers, shared workflow config, or review/merge policy behavior; do not inflate unrelated tasks with generic process boilerplate.
- Before changing shared workflow helpers or shared workflow config, enumerate every caller that depends on the shared behavior.
- When shared workflow behavior changes, add at least one regression test for an unaffected caller so the change does not silently break other workflow entry points.
- Before changing review, comment, or reaction handling in merge policy logic, define the current-head and current-window semantics for each signal and regression-test both the intended pass path and at least one stale or non-applicable signal path.

After completing work:
- Update `tasks/CURRENT_SPRINT.md` (mark DONE) and move finished tasks to `tasks/COMPLETED.md`.
- Keep `PROJECT_STATUS.md` as a non-authoritative stub that points to the active ledgers and archive; do not rebuild it into a live status ledger.
- Preserve full closed-task bodies in `archive/closed_tasks/YYYY-QN.md`; keep that archive opt-in only and out of normal implementation context.
- Add/adjust ADRs under `docs/adr/` for major decisions.
- Ensure formatting/linting/tests pass.

## Guardrails

- Don’t introduce network calls in tests.
- Keep probability updates explainable (store factors used for deltas).
- Any LLM usage must be protected by budget/limits where possible.

## Agent Tooling Policy

- `.claude/settings.local.json` is a local override and must remain untracked.
- Keep only `.claude/settings.example.json` versioned as the baseline policy.
- Local setup instructions live in `.claude/README.md`.

## Human-Gated Tasks

- Task entries may include the label `[REQUIRES_HUMAN]`.
- Any task marked `[REQUIRES_HUMAN]` is blocked for autonomous execution.
- Agents must not implement, close, or mark those tasks DONE until a human explicitly confirms manual completion.
- Agents may prepare scaffolding/checklists for `[REQUIRES_HUMAN]` tasks, but must stop before the manual step and report that human action is required.
- Required `[REQUIRES_HUMAN]` delivery sequence:
  1. Create/switch to the task branch.
  2. Scaffold checklist/context files first, then run back-and-forth review with the human.
  3. Finalize implementation only after that review.
  4. Open/update PR for the finalized task scope.
  5. Merge only after explicit human sign-off in-thread (for example: `Approved`, `Go`, `Sign off`).
  6. After merge, switch to `main` and sync (`git pull --ff-only`).
- Do not merge a `[REQUIRES_HUMAN]` task PR before explicit human sign-off, even if CI is green.

## Task Branching and PR Rules (Hard Rule)

- Every engineering task must run on its own dedicated git branch created from `main`.
- Branch scope must be single-task only (no mixed `TASK-XXX` implementation in one branch).
- Before creating a task branch, run sequencing preflight: `uv run --no-sync horadus tasks preflight`.
- Start task branches via lower-level guarded command: `uv run --no-sync horadus tasks start TASK-XXX --name short-name`.
- Canonical agent start command is `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name` (enforces sprint eligibility + sequencing guard, and can carry forward eligible planning-intake edits for the target task).
- `make task-preflight`, `make task-start`, and `make agent-safe-start` remain compatibility wrappers when a Make target is more convenient.
- Prefer `horadus` for repo workflow operations when an equivalent command
  exists (for example `horadus tasks ...` and `horadus triage collect`), and
  prefer `--format json` for agent consumption where appropriate.
- Task start is blocked unless `main` is synced and there is no open non-merged task PR for the current operator. Dirty working trees remain blocked by default; only eligible planning-intake edits for the target task may carry forward through `horadus tasks start` / `safe-start`. Eligible intake is limited to shared live task ledgers plus target-task planning artifacts (`tasks/exec_plans/TASK-XXX.md` and task-owned `tasks/specs/` files).
- Open one PR per task branch and merge only after required checks are green.
- Every task PR title must be `TASK-XXX: short summary` matching the branch task ID.
- Every task PR body must include exactly one canonical metadata line: `Primary-Task: TASK-XXX` matching the branch task ID.
- Before merge, the PR head must already contain the task-close state: remove the primary task from live `tasks/BACKLOG.md` and `tasks/CURRENT_SPRINT.md`, add it to `tasks/COMPLETED.md`, and archive the full task body under `archive/closed_tasks/YYYY-QN.md`.
- After merge, delete the task branch to avoid stale branch drift.
- Task start sequence is mandatory: `git switch main` → `git pull --ff-only` → create/switch task branch.
- Task completion sequence is mandatory: merge PR → delete branch → `git switch main` → `git pull --ff-only` and verify the merge commit exists locally.
- Mechanical completion for a task is defined by `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`; success requires the verifier to report `local-main-synced`.
- Default autonomous completion for engineering tasks is full delivery lifecycle (implement → commit → push → PR → green checks → merge → local main sync), not just local code changes.
- Do not skip prerequisite workflow steps such as preflight, guarded task start, or context collection just because the likely end state looks obvious.
- Prefer Horadus workflow commands over raw `git` / `gh` when the CLI covers the step because the CLI encodes sequencing, policy, and verification dependencies rather than just style.
- Keep using the workflow until prerequisite checks, required verification reruns, and completion verification succeed; do not stop at the first plausible success signal.
- Treat an empty, partial, or suspiciously narrow workflow result as a retrieval problem first when the missing data likely exists.
- Before concluding that no result exists, try one or two sensible recovery steps such as broader Horadus queries, alternate filters, or the documented manual recovery path.
- If a forced fallback is still required after those recovery attempts, record it with `horadus tasks record-friction`; do not log routine success cases or expected empty results.
- Treat repo-facing work as incomplete until requested deliverables, required repo updates, and required verification/gate runs are finished or explicitly reported blocked.
- Implementation, required tests/gates, and required task/doc/status updates remain part of the same task unless they are explicitly blocked.
- If a task is blocked, report the exact missing item, the blocker causing it, and the furthest completed lifecycle step rather than a vague partial-completion claim.
- Do not claim a task is complete, done, or finished until `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict` passes or `horadus tasks finish TASK-XXX` completes successfully.
- The default review-gate timeout for `horadus tasks finish` is 600 seconds (10 minutes). Agents must not override it unless a human explicitly requested a different timeout.
- Do not proactively suggest changing the `horadus tasks finish` review timeout; wait the canonical 10-minute window unless the human explicitly asked otherwise.
- A `THUMBS_UP` reaction from the configured reviewer on the PR summary counts as a positive review-gate signal; once current-head required checks are green, `horadus tasks finish` may continue early on that signal while still blocking actionable current-head review comments.
- `horadus tasks finish` must treat current-head review feedback, required checks, and unresolved review threads as the merge gate for the current PR head. A silent timeout after the full wait window may still continue only when current-head required checks are still green and no unresolved current-head review threads still block the PR. Outdated unresolved review threads do not count as blockers and should be auto-resolved by the CLI when GitHub still treats them as merge blockers. If the PR head changes during or between finish invocations after review work starts, the CLI must immediately revalidate current-head merge readiness, auto-resolve outdated unresolved older-head review threads, request fresh review once for the new head when needed, discard the older review-window context, and start a fresh review window. On the same-head unresolved-thread timeout path it should also request a fresh `@codex review` automatically.
- `horadus tasks finish` blocks before merge if the task-close state is missing on the PR head or if the local task branch head, pushed branch head, and PR head differ; outdated or already-resolved review threads do not count as blockers.
- If a prior `horadus tasks finish TASK-XXX` run leaves you back on `main` before the PR lifecycle is actually complete, re-run the same command with the explicit task id before treating the CLI as unavailable or falling back to raw `gh pr merge`.
- Local commits, local tests, and a clean working tree are checkpoints, not completion.
- Do not stop at a local commit boundary unless the user explicitly asked for a checkpoint.
- Resolve locally solvable environment blockers before reporting blocked.
- If any lifecycle step is blocked (permissions/CI/platform), stop at the furthest completed step and report the exact blocker and required manual action.
- If unrelated work is discovered mid-task, create a new task immediately but do not switch branches by default; continue current task unless the new work is a blocker/urgent.
- Never mix two tasks in one commit/PR; blockers must be handled via a separate task branch after a safe checkpoint.
- Backlog capture rule for discovered follow-ups:
  - If new backlog tasks are discovered during `TASK-XXX` and are relevant to that task scope, add them in the same `TASK-XXX` branch/PR (prefer a separate docs commit in that branch).
  - Split backlog edits to a separate task branch only when: scope is unrelated, the original task is already merged/closed, or an urgent blocker requires immediate isolation.
  - Before merge, verify backlog updates were either included in-branch or explicitly split with rationale in PR/task notes.

## Implementation Pointers (Keep It Lean)

- Clustering threshold semantics: check `src/processing/event_clusterer.py` and `docs/ARCHITECTURE.md`.
- Probability math and log-odds helpers: `src/core/trend_engine.py`.
- LLM budget/retry/failover policy: `src/processing/` and ADRs in `docs/adr/`.
- Treat this file as a router; keep detailed implementation recipes in module docs/runbooks.

## Development Commands

- Repo workflow CLI:
  - `uv run --no-sync horadus tasks preflight`
  - `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
  - `uv run --no-sync horadus tasks context-pack TASK-XXX`
  - `make agent-check`
  - `uv run --no-sync horadus tasks local-gate --full`
  - `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
  - `uv run --no-sync horadus tasks finish TASK-XXX`
  - `uv run --no-sync horadus tasks record-friction TASK-XXX --command-attempted "..." --fallback-used "..." --friction-type forced_fallback --note "..." --suggested-improvement "..."`
- `uv run --no-sync horadus tasks list-active --format json`
  - `uv run --no-sync horadus triage collect --lookback-days 14 --format json`
- Record friction only for real Horadus workflow gaps or forced fallback, not
  routine success cases. Entries live under gitignored
  `artifacts/agent/horadus-cli-feedback/` and should not be read during normal
  task execution.
- Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
  needed workflow step yet, or when the CLI explicitly tells you a manual
  recovery step is required. A review-gate timeout handled inside
  `horadus tasks finish` is not a manual-recovery signal.
- Tests: `pytest tests/ -v`
- Dev API: `uvicorn src.api.main:app --reload`
- Format/lint: `ruff format src/ tools/ tests/` and `ruff check src/ tools/ tests/`
- Typecheck: `mypy src/ tools/horadus/python`

## Git Conventions

Branch naming:
- Task branches are enforced as `codex/task-XXX-short-name` via `horadus tasks start`.
- `main` is protected and must stay merge-only.

Commit message format:
- `<type>(<scope>): <subject>`
- Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`
- Scope (optional): `api`, `core`, `storage`, `ingestion`, `processing`, `workers`, `repo`

Commit hygiene:
- Keep commits atomic (one logical change).
- Include `TASK-XXX` in body/footer when applicable.
- Prefer subject ≤ 50 chars; wrap body at ~72 chars.

## Environment Variables

Copy `.env.example` to `.env`. LLM provider selection is documented in `docs/adr/002-llm-provider.md`.

Typical required values:
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY` (don’t commit real keys)
