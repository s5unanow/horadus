# Agent Runbook

**Last Verified**: 2026-03-14

Short command index for day-to-day agent/operator work.

Use this file for executable command references and quick operator notes.
Use `AGENTS.md` for canonical workflow policy and completion rules, and use
`README.md` for repo navigation plus setup pointers.

CLI implementation ownership now lives entirely under
`tools/horadus/python/horadus_cli/`. The installed `horadus` entrypoint points
directly at that package, and app-backed CLI commands cross the explicit
runtime bridge at `tools/horadus/python/horadus_app_cli_runtime.py` instead of
importing business modules into the tooling package.

Default live planning surfaces are `tasks/CURRENT_SPRINT.md`,
`tasks/BACKLOG.md`, and `tasks/COMPLETED.md`. Treat `PROJECT_STATUS.md` as a
pointer stub only, and do not read `archive/` or `archive/closed_tasks/`
unless the user explicitly asks for historical context or you pass an
archive-aware CLI flag.

For RFC/design work, use the review checklist in `docs/rfc/README.md` before
circulating a proposal for implementation planning.

## Canonical Commands

1. `uv run --no-sync horadus tasks preflight`
When: before creating a task branch from `main`.
This stays conservative: it still fails on dirty working trees, but when the
only dirty files are task-ledger candidates it should point you back to the
task-specific guarded start flow instead of forcing guesswork.

2. `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
When: canonical autonomous task-start command; enforces sprint eligibility and
sequencing checks before creating the task branch.
If the only dirty files are eligible planning-intake edits for the target
task (shared live task ledgers plus target-task planning artifacts like
`tasks/exec_plans/TASK-XXX.md` or a task-owned file under `tasks/specs/`), the
command carries them onto the new task branch and reports which files were
treated as eligible versus which files still block branch creation.

Compatibility wrapper:
- `make agent-safe-start TASK=XXX NAME=short-name`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks safe-start` flow.

3. `uv run --no-sync horadus tasks context-pack TASK-XXX`
When: collect backlog/spec/sprint context for an implementation task.
Use `tasks/specs/TEMPLATE.md` when a task needs a new or refreshed spec; keep
the contract explicit around problem statement, inputs, outputs, non-goals, and
acceptance criteria.
For planning-gate applicability, use one marker scheme everywhere:
- `**Planning Gates**: Required — reason`
- `**Planning Gates**: Not Required — reason`
Marker precedence is deterministic:
- exec plan marker when an exec plan exists
- otherwise spec marker
- otherwise backlog-entry marker
- if no explicit marker exists, `Exec Plan: Required` means planning gates are
  required by default
Shared workflow/policy changes should opt into the same marker scheme rather
than relying on narrative-only guidance.
`context-pack` now surfaces the planning state automatically for applicable
tasks:
- authoritative artifact present
- spec-backed without exec plan
- backlog-only / missing artifact
Non-applicable tasks stay on the quiet path with no planning banner.
For high-risk cross-surface tasks (for example migrations, shared workflow
tooling or config, shared math, or multi-surface mutation work), front-load
adversarial review before the first push instead of discovering the whole bug
set inside `horadus tasks finish`.
`context-pack` surfaces the pre-push review block only when the repo-owned
heuristic sees the relevant workflow/policy/config, math, or multi-surface
runtime signals, instead of on every ordinary task.
`context-pack` also surfaces caller-aware validation packs for shared helper
and shared math tasks. When a pack appears, run its dependent suites in
addition to the baseline gates; shared Python helpers and shared math both
require explicit full-repo type checking via `make typecheck`.
If planning gates are required but the backlog entry is still the only artifact,
create the missing spec or exec plan before implementation and use
`tasks/specs/275-finish-review-gate-timeout.md` as the canonical example.
Use `--include-archive` only when the task is no longer live and the user
explicitly needs archived history.

4. `uv run --no-sync horadus tasks close-ledgers TASK-XXX`
When: move a completed task out of the live ledgers, append its full task block
to `archive/closed_tasks/YYYY-QN.md`, and update `tasks/CURRENT_SPRINT.md` plus
`tasks/COMPLETED.md` before merge.

5. `make agent-check`
When: fast local quality gate (lint + typecheck + code-shape + unit tests).
This covers tracked Python under `src/`, `tools/`, and `scripts/`.
The workflow unit suite includes the repo-owned import-boundary analyzer for
`src/` dependency direction, tooling package boundaries, and the explicit
runtime bridge seam into app code.
This is still a baseline gate, not a substitute for task-specific targeted
tests when the task changes code, config, or repo-workflow behavior.

6. `uv run --no-sync horadus tasks local-gate --full`
When: canonical post-task local gate before push/PR; runs the full CI-parity
local validation sequence without replacing the fast iteration gate.
The full gate also runs the repo-owned code-shape checker, which enforces the
current module/function line budgets, member cyclomatic-complexity budgets,
and ratcheting limits for explicitly tracked legacy hotspots in
`config/quality/code_shape.toml`.
It also fail-closes on repo-owned eval dataset-quality/provenance checks that
previously lived partly as opt-in commands.
The unit-coverage step fails closed at `100%` measured coverage for `src/` and
the workflow tooling home under `tools/`, plus tracked Python under `scripts/`,
using the same repo-owned coverage gate script that CI and the pre-push hook
call, so local and remote enforcement stay aligned.
The matching server-side security substeps also have direct local entry points:
- `make secret-scan` and the pre-commit `secret-scan` hook both run the
  repo-owned tracked-file scanner via `./scripts/run_secret_scan.sh`, which
  applies the canonical policy from
  `config/security/secret_scan_policy.json` against `.secrets.baseline`
- `make dependency-audit` runs the locked-project vulnerability audit used by CI
  and applies only the exact repo-owned allowlist entries recorded in
  `config/security/dependency_audit_allowlist.json`
If the gate reaches the Docker-backed integration step and the daemon is not
ready, it attempts best-effort local auto-start on supported environments
before failing with a specific blocker.
If `UV_BIN` is set to an absolute `uv` path, every `uv`-backed full-gate step
uses that same executable, including package-build validation.
Keep this as the canonical strict post-task local gate. If a task touches
integration-covered paths or push/PR workflow surfaces, run
`make test-integration-docker` as focused proof when helpful, but do not treat
that narrower command as a replacement for the full gate.

Compatibility wrapper:
- `make local-gate`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks local-gate --full` flow.
- Coverage debug path:
  - `make test-unit-cov` for the same hard-fail unit coverage gate outside the
    full workflow
  - Use the `term-missing` output to inspect the missing files/lines/branches
    before re-running the full gate

7. `make agent-smoke-run`
When: one-shot API serve + smoke + exit without orphan processes.

8. `make doctor`
When: diagnose local config/DB/Redis readiness quickly.

9. `uv run --no-sync horadus triage collect --lookback-days 14 --format json`
When: collect current sprint/backlog/completed/assessment inputs for backlog triage.
Keyword/path/proposal matches now default to deduplicated task-aware records
with `task_id`, title, status, matched fields, and concise context excerpts.
Recent assessments now default to grouped per-role summaries with latest
artifact metadata; use `--assessment-path-limit N` for a bounded path preview
or `--include-assessment-paths` for the full path list. Use `--include-raw`
only when line-level hit details are explicitly needed.

10. `uv run horadus pipeline dry-run --fixture-path ai/eval/fixtures/pipeline_dry_run_items.jsonl`
When: deterministic no-network/no-LLM regression exercise.

11. `make release-gate RELEASE_GATE_DATABASE_URL=<db-url>`
When: full pre-release checks before promotion.
This now reuses the canonical `horadus tasks local-gate --full` contract and
then adds the release-only migration-drift gate for the target database.

12. `uv run --no-sync horadus tasks lifecycle TASK-XXX --strict`
When: inspect machine-checkable task lifecycle state.
Use the strict form to verify repo-policy completion; success requires state
`local-main-synced`.
When running from detached `HEAD` (for example in CI or a throwaway worktree),
pass the task id explicitly; branch inference is only supported on canonical
task branches.

13. `uv run --no-sync horadus tasks finish TASK-XXX`
When: canonical task-completion command; finishes the current task PR lifecycle
(branch/task verification -> missing-branch push / missing-PR bootstrap when
needed -> pushed branch/PR checks -> current-head review gate
-> merge -> local `main` sync -> strict lifecycle verification).
Task PRs must be titled `TASK-XXX: short summary` and include exactly one
`Primary-Task: TASK-XXX` line in the body.
If the next required action is a Docker-gated push and Docker is not ready, the
command attempts supported local auto-start before returning a blocker.
When bootstrapping, `finish` deduplicates by open head branch first; task-id PR
search remains lifecycle recovery, not the bootstrap dedupe key.
If you rerun `finish` after pushing a new PR head, the CLI refreshes stale
older-head review state, requests fresh current-head review when needed, and
starts a fresh review window before waiting again.
During the review window, `finish` emits periodic status that includes the
reviewer, current PR head, and remaining time / deadline so the wait does not
look hung.
Before entering that wait, `finish` now surfaces unresolved current-head review
threads immediately. If GitHub still marks older-head-fixed threads as current,
the blocker text tells you to inspect and resolve the stale-current threads
manually before rerunning.
If a same-head review window already timed out and the only remaining blocker
is unresolved review threads, resolving those threads and rerunning `finish`
can continue on the same head without silently restarting a fresh timeout
window.
Before invoking `finish`, the task still owes its targeted proofs: run relevant
task-specific tests for code/config/workflow changes, update docs when
behavior/workflow/operator-facing contracts changed, and record any N/A or
waived proof in the task's authoritative planning artifact when one exists.
For completion policy, review-timeout semantics, fresh re-review ownership,
thread handling, and completion-claim rules, see `AGENTS.md`.

Compatibility wrapper:
- `make task-finish`
- Use only when a Make target is more convenient; it must delegate to the same
  `horadus tasks finish` flow.

Use raw `git` / `gh` commands only when the Horadus CLI does not expose the
needed workflow step yet, or when the CLI explicitly tells you a manual
recovery step is required.
A missing PR alone is no longer a manual-recovery signal for `finish`.

14. `uv run --no-sync horadus tasks intake add --title "..." --note "..." [--ref "..."] [--source-task TASK-XXX]`
When: capture a non-authoritative follow-up locally without editing tracked ledgers.
The intake log lives under the gitignored `artifacts/agent/task-intake/entries.jsonl`
path, so normal capture does not create tracked task-ledger diffs.
Use `uv run --no-sync horadus tasks intake list` to review pending intake items,
`uv run --no-sync horadus tasks intake groom --intake-id INTAKE-XXXX --dismiss`
or `--restore` to batch-triage them, and
`uv run --no-sync horadus tasks intake promote INTAKE-XXXX --priority ... --estimate ... --acceptance "..."`
only when you are deliberately writing a canonical backlog entry.
Keep same-scope work in the current task branch; use intake for unrelated or later
follow-ups that should wait for grooming.

15. `uv run --no-sync horadus tasks record-friction TASK-XXX --command-attempted "..." --fallback-used "..." --friction-type forced_fallback --note "..." --suggested-improvement "..."`
When: record a real Horadus workflow gap or forced fallback in a structured
local friction log under `artifacts/agent/horadus-cli-feedback/`.
Use this only for genuine friction or forced fallback after sensible recovery
attempts, not routine success cases or expected empty results, and do not
treat the log as required reading during normal task flow.

16. `uv run --no-sync horadus tasks automation-lock check --automation-id <id>`
When: inspect or recover the repo-owned external lock path used by a Codex automation.
Use `automation-lock lock --automation-id <id> --owner-pid "$PPID"` to acquire the lock and `automation-lock unlock --automation-id <id> --owner-pid "$PPID"` to release it when the caller is a markdown-driven automation step.
Use another `--owner-pid <stable-process-pid>` value only when the caller can provide a long-lived owner PID that survives across helper invocations.
This is the portable replacement for host-specific `flock` usage in the sprint autopilot path.

17. `uv run --no-sync horadus tasks summarize-friction --date YYYY-MM-DD`
When: generate the compact daily friction report at
`artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md`.
The report groups duplicate patterns, highlights candidate CLI/skill
improvements, and keeps follow-up work in human-review-only form. Do not
auto-create backlog tasks from the report.

18. `make test-integration-docker`
When: run integration tests locally in an ephemeral Docker stack (safe defaults).
Note: the repo `pre-push` hook runs the same gate by default; bypass only with
`HORADUS_SKIP_INTEGRATION_TESTS=1` for exceptional cases.
If Docker auto-start is unsupported in the current environment, start Docker
manually before rerunning the workflow command.

## Optional Local Review

`uv run --no-sync horadus tasks local-review --format json`

When: run an opt-in local pre-push review against the current branch diff
without opening a PR. The default target is the current branch against `main`,
and the command returns a repo-owned JSON/text result instead of a
provider-specific stdout contract.

Provider selection:
- `--provider` overrides the configured default for the current run.
- Absent `--provider`, the command reads `HORADUS_LOCAL_REVIEW_PROVIDER` from
  optional local-only `.env.harness` when present.
- If neither is set, the repo default provider is `claude`.

Fallback behavior:
- Missing provider CLIs on `PATH` can fall back to the next supported provider
  in repo order when the command is using the env/default provider chain.
- Auth, config, runtime, or unreadable-output failures stay visible by default;
  use `--allow-provider-fallback` only when you explicitly want the command to
  try another provider after those failures.

Artifacts and scope:
- Telemetry appends to the gitignored
  `artifacts/agent/local-review/entries.jsonl` log.
- `--save-raw-output` keeps per-run raw provider output under
  `artifacts/agent/local-review/runs/`.
- Provider subprocess runs are bounded to 180 seconds; a hung provider returns
  a repo-owned failure with timeout diagnostics instead of hanging indefinitely.
- Claude and Gemini run against the repo-owned prompt contract directly;
  Codex uses its native `review --base` flow and Horadus normalizes the review
  result into the same local-review surface.
- Use this command for advisory local branch-diff review before push; keep
  remote PR review and `horadus tasks finish` as the merge gate.
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

## Finish Debug Surface

- `HORADUS_FINISH_DEBUG=1 uv run --no-sync horadus tasks finish TASK-XXX`

When: capture extra finish-path diagnostics for checks, review gate, merge, and
sync transitions without changing merge policy or timeout policy.

## Eval Benchmark Configs

- `uv run --no-sync horadus eval benchmark` runs only the default baseline
  configs: `baseline` and `alternative`.
- GPT-5 benchmark candidates stay available for targeted comparisons, but must
  be requested explicitly with repeated `--config` flags.

## Research-Heavy Workflows

- Use bounded research mode only for triage, assessments, architecture review
  intake, and similar synthesis-heavy workflows, not for ordinary
  implementation tasks.
- Bounded research mode is: plan the sub-questions, retrieve only the repo
  evidence needed to answer them, then synthesize with explicit contradiction
  handling and clear labeling of directly supported fact versus inference.
- Cite the exact file path, task id, proposal id, or command output that backs
  each research claim; do not invent sources or smooth over conflicting
  evidence.

## Shared Workflow/Policy Guardrails

See `AGENTS.md` for the canonical shared-workflow guardrails and merge-policy
rules.
