# Horadus CLI Command Notes

This reference covers the repo-owned `horadus` command surfaces that agents
should check before falling back to raw file parsing, scripts, `git`, or `gh`.
For canonical workflow policy, blocker handling, and merge/review semantics,
read `AGENTS.md`.

Implementation note:
- CLI ownership lives under `tools/horadus/python/horadus_cli/`.
- The installed `horadus` entrypoint points directly at the tooling package.
- App-backed commands cross `tools/horadus/python/horadus_app_cli_runtime.py`
  instead of importing business-app modules into the tooling package.

Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
needed workflow step yet, or when the CLI explicitly tells you a manual
recovery step is required.

## Root command groups

- `uv run --no-sync horadus trends status`
  - Inspect trend probabilities.
- `uv run --no-sync horadus dashboard export`
  - Export dashboard artifacts.
- `uv run --no-sync horadus eval benchmark`
  - Run offline benchmark evals.
- `uv run --no-sync horadus pipeline dry-run`
  - Run pipeline fixture exercises.
- `uv run --no-sync horadus agent smoke`
  - Run local agent smoke checks.
- `uv run --no-sync horadus doctor`
  - Run local runtime diagnostics for hooks, config, DB, Redis, and migrations.
- `uv run --no-sync horadus tasks list-active`
  - Inspect active sprint tasks and human blocker metadata.
- `uv run --no-sync horadus triage collect`
  - Produce a structured bundle for weekly backlog triage and automation input.

## Task lifecycle

- `uv run --no-sync horadus tasks preflight`
  - Enforces clean/synced `main`, required hooks, GitHub CLI availability, and
    task-PR sequencing before branch creation.
- `uv run --no-sync horadus tasks assert-safe-worktree`
  - Fails closed when tracked diffs already exist on `main` during chat/agent
    work; skips on non-`main` branches.
- `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
  - Canonical autonomous task-start command; enforces sprint eligibility and
    then creates the canonical `codex/task-XXX-short-name` branch.
- `uv run --no-sync horadus tasks context-pack TASK-XXX --mode implement --format json`
  - Returns task scope, likely files, caller-aware validation, and workflow
    requirements for implementation-mode agent work.
- `uv run --no-sync horadus tasks close-ledgers TASK-XXX`
  - Records the in-branch task-close state by moving the task out of live
    ledgers, adding the compact completion entry, and archiving the full body.
- `make agent-check`
  - Fast inner-loop gate for formatting, linting, type checks, code shape, and
    unit tests.
- `uv run --no-sync horadus tasks local-review --format json`
  - Runs advisory local pre-push review against the current branch diff.
- `uv run --no-sync horadus tasks local-gate --full`
  - Canonical strict local validation gate before push/PR.
- `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
  - Mechanical lifecycle verifier; final success requires local main sync after
    merge.
- `uv run --no-sync horadus tasks finish TASK-XXX`
  - Canonical completion command. It owns missing-branch push, missing-PR
    bootstrap, required-check/review readiness, merge, branch cleanup, and local
    `main` sync when policy allows.

## Task discovery and follow-ups

- `uv run --no-sync horadus tasks show TASK-XXX --format json`
  - Return a live or archived task record.
- `uv run --no-sync horadus tasks search "query" --format json`
  - Search backlog task title, description, files, and acceptance criteria.
- `uv run --no-sync horadus tasks eligibility TASK-XXX --format json`
  - Check sprint activeness, human-gated status, and task-start preflight.
- `uv run --no-sync horadus tasks start TASK-XXX --name short-name --dry-run --format json`
  - Lower-level guarded branch-start dry run when eligibility was handled
    separately.
- `uv run --no-sync horadus tasks intake add --title "..." --note "..." [--ref "..."] [--source-task TASK-XXX]`
  - Capture a non-authoritative follow-up in the gitignored local intake log.
- `uv run --no-sync horadus tasks intake list`
  - Review pending intake entries.
- `uv run --no-sync horadus tasks intake groom --intake-id INTAKE-XXXX --dismiss`
  - Dismiss or restore local intake during grooming.
- `uv run --no-sync horadus tasks intake promote INTAKE-XXXX --priority ... --estimate ... --acceptance "..."`
  - Deliberately write a canonical backlog entry from local intake.
- `uv run --no-sync horadus tasks record-friction TASK-XXX --command-attempted "..." --fallback-used "..." --friction-type forced_fallback --note "..." --suggested-improvement "..."`
  - Record a real Horadus workflow gap or forced fallback under the gitignored
    feedback log.
- `uv run --no-sync horadus tasks summarize-friction --date YYYY-MM-DD`
  - Generate the grouped daily friction report for human review.

## Automation lock

- `uv run --no-sync horadus tasks automation-lock check --automation-id <id>`
  - Inspect or recover a repo-owned external lock for markdown-driven
    automation.
- `uv run --no-sync horadus tasks automation-lock lock --automation-id <id> --owner-pid "$PPID"`
  - Acquire a lock for the current automation owner process.
- `uv run --no-sync horadus tasks automation-lock unlock --automation-id <id> --owner-pid "$PPID"`
  - Release the matching lock owner.

## Eval commands

- `uv run --no-sync horadus eval benchmark`
  - Run default benchmark configs, currently `baseline` and `alternative`.
- `uv run --no-sync horadus eval benchmark --tier-scope tier1`
  - Run Tier 1-only gold-set diagnostics while skipping Tier 2 calls and still
    preserving benchmark result artifacts.
- `uv run --no-sync horadus eval benchmark --tier-scope tier2`
  - Run Tier 2-only gold-set diagnostics while skipping Tier 1 calls and still
    preserving benchmark result artifacts.
- `uv run --no-sync horadus eval benchmark --config gpt-5-mini --config gpt-5`
  - Run explicit benchmark candidate comparisons.
- `uv run --no-sync horadus eval audit`
  - Inspect benchmark artifacts for validity and regressions.
- `uv run --no-sync horadus eval behavior`
  - Run the full deterministic behavior-eval pack.
- `uv run --no-sync horadus eval behavior --suite context-retrieval`
  - Run implement-mode context retrieval behavior checks.
- `uv run --no-sync horadus eval behavior --suite taxonomy-safety`
  - Run deterministic taxonomy and indicator-selection safety checks.
- `uv run --no-sync horadus eval behavior --suite degraded-mode-safety`
  - Run degraded-mode holding and provisional extraction checks.
- `uv run --no-sync horadus eval behavior --suite report-grounding`
  - Run report grounding behavior checks.
- `uv run --no-sync horadus eval behavior --tag grounding`
  - Run only behavior cases tagged for grounding contracts.
- `uv run --no-sync horadus eval validate-taxonomy`
  - Validate taxonomy mapping safety.
- `uv run --no-sync horadus eval replay`
  - Replay captured eval artifacts.
- `uv run --no-sync horadus eval regression-intake`
  - Convert eval findings into structured regression-intake artifacts.
- `uv run --no-sync horadus eval code-health`
  - Compare changed tracked Python files with code-shape metrics and emit a
    deterministic structural-regression artifact.
- `uv run --no-sync horadus eval vector-benchmark`
  - Benchmark exact, IVFFlat, and HNSW retrieval quality/latency.
- `uv run --no-sync horadus eval embedding-lineage`
  - Report embedding model lineage and re-embed scope.
- `uv run --no-sync horadus eval source-freshness`
  - Report stale RSS/GDELT sources and catch-up candidates.

## Local review notes

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
- Provider precedence is: `--provider`, then
  `HORADUS_LOCAL_REVIEW_PROVIDER` from optional local-only `.env.harness`, then
  the repo default `claude`.
