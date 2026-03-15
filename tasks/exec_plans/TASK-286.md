# TASK-286: Add CLI-Agnostic Local Pre-Push Review via Supported Agent CLIs

## Status

- Owner: Codex
- Started: 2026-03-15
- Current state: In progress after sprint admission and 2026-03-15 human
  approval of the local-review contract
- Planning Gates: Required — shared workflow behavior, multi-provider CLI
  integration, and docs/skill/test alignment all change together

## Goal (1-3 lines)

Add a repo-owned local pre-push review step under `horadus tasks ...` that
uses a provider-neutral command contract and thin provider adapters so the repo
can support Codex CLI, Claude Code, and Gemini CLI without baking one vendor's
interface into the public workflow.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-286`), `AGENTS.md`,
  `docs/AGENT_RUNBOOK.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_cli/`,
  `tools/horadus/python/horadus_workflow/`, `Makefile`, `.gitignore`,
  `.env.harness`, `ops/skills/horadus-cli/`, `tests/unit/`, `tests/workflow/`
- Preconditions/dependencies:
  - keep the public entrypoint on the canonical `horadus tasks ...` surface
  - preserve `v2` task-workflow ownership boundaries
  - support at least Codex CLI, Claude Code, and Gemini CLI without requiring
    GitHub PR state
  - `TASK-286` now appears in `tasks/CURRENT_SPRINT.md`
  - 2026-03-15 human approval cleared implementation for this
    `[REQUIRES_HUMAN]` task
  - make provider precedence explicit: CLI override first, then
    `HORADUS_LOCAL_REVIEW_PROVIDER` from optional local-only `.env.harness`,
    then the repo default `claude`
  - keep fallback behavior explicit: auto-fallback applies only when the
    selected provider CLI is missing on `PATH`; auth/config/runtime failures
    require an explicit `--allow-provider-fallback` opt-in before trying a
    second provider
  - keep invocation opt-in in this task; do not wire local review into
    `local-gate`, `finish`, or git hooks yet
  - keep generated review telemetry and optional raw outputs only under
    gitignored `artifacts/agent/local-review/` paths so they do not pollute
    tracked source paths or task diffs

## Outputs

- Expected behavior/artifacts:
  - canonical local-review workflow command with provider selection/defaulting
  - `.env.harness`-backed default provider via
    `HORADUS_LOCAL_REVIEW_PROVIDER`, with `claude` as the default provider
  - thin provider adapters for Codex CLI, Claude Code, and Gemini CLI
  - normalized local-review prompt/input contract for base diff, optional
    review instructions, output capture, and findings reporting
  - structured stdout result via `--format json` (or equivalent) as the
    canonical machine-consumable command output for agents
  - lightweight per-run usefulness tracking for later policy evaluation
  - gitignored telemetry at `artifacts/agent/local-review/entries.jsonl`, with
    optional per-run raw outputs under `artifacts/agent/local-review/runs/`
  - explicit exit-status contract: successful review runs return `0` even when
    findings are reported; invalid context or provider failures remain
    non-zero
  - updated runbook/skill/reference docs and regression coverage
- Validation evidence:
  - focused CLI/workflow tests for each supported provider shape
  - at least one unaffected shared-caller regression path
  - canonical local gate after implementation

## Non-Goals

- Explicitly excluded work:
  - changing remote PR review automation or `@codex review` semantics
  - making local review a required gate in `local-gate`, `finish`, or git
    hooks in this task
  - introducing a provider plugin system broader than the initial supported
    adapter seam
  - requiring live network calls to validate provider behavior in tests
  - choosing a single vendor-specific public interface for the repo workflow

## Scope

- In scope:
  - repo-owned command contract for local pre-push review
  - env-backed default provider selection plus explicit per-run override
  - adapter seams for Codex CLI, Claude Code, and Gemini CLI
  - explicit opt-in invocation policy and lightweight usefulness telemetry
  - explicit telemetry schema and gitignored storage location for local-review
    runs
  - provider-specific error handling, docs, and test fixtures
  - artifact path handling that avoids polluting the reviewed diff
- Out of scope:
  - generic agent orchestration unrelated to local review
  - changes to task start/finish workflow semantics
  - support for additional CLIs unless they fit the same seam with no contract
    changes

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: extend the existing `horadus tasks`
  workflow with one repo-owned local-review contract and keep provider-specific
  flags/prompts inside thin adapters
- Accepted provider precedence: explicit `--provider` overrides
  `HORADUS_LOCAL_REVIEW_PROVIDER` from `.env.harness`; absent both, default to
  `claude`
- Accepted fallback policy: auto-fallback only when the selected provider CLI
  is missing on `PATH`; auth/config/runtime failures require explicit
  `--allow-provider-fallback` opt-in before trying another provider
- Accepted fallback order: explicit `--provider` tries only that provider by
  default; otherwise start with the env/default provider and then try remaining
  supported providers in repo order `claude` -> `codex` -> `gemini`, skipping
  any provider already attempted
- Accepted invocation policy: keep local review explicit and opt-in for now;
  gather usefulness data before deciding whether any later task should make it
  mandatory
- Accepted telemetry shape: append one JSONL entry per run to
  `artifacts/agent/local-review/entries.jsonl`; if raw model output needs to be
  retained for debugging, store it under `artifacts/agent/local-review/runs/`
  instead of tracked source paths or ad hoc repo-root files
- Accepted machine-consumption contract: expose structured stdout through
  `--format json` (or equivalent) as the canonical per-run result for agents;
  treat the append-only JSONL log as audit/telemetry rather than the primary
  integration surface
- Accepted exit-status policy: a review run that completes successfully exits
  `0` even when findings are reported; use the command output and telemetry to
  convey findings, and reserve non-zero exit codes for invalid invocation,
  missing provider CLIs, or provider execution failures
- Rejected simpler alternative: wrapping only `codex review` would immediately
  hardcode one vendor's interface and leave Claude Code / Gemini CLI users
  without a supported path
- First integration proof: focused workflow tests that exercise one dedicated
  review-style provider path and one prompt-only provider path
- Waivers: None

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - confirm supported local CLI interfaces and choose the smallest repo-owned
     contract that spans them
   - define provider precedence and env/config loading behavior before wiring
     adapters
   - define `.env.harness` as optional local-only config and keep the repo
     ignore policy aligned with that expectation
   - define and document which failure classes permit auto-fallback and which
     require explicit `--allow-provider-fallback`
   - define the repo fallback order `claude` -> `codex` -> `gemini` for
     non-explicit-provider runs, skipping providers already attempted
   - define the minimum usefulness telemetry fields and gitignored artifact
     paths without turning the command into another heavy workflow gate
   - enumerate every shared caller that depends on the workflow behavior before
     helper changes land
2. Human Review Checkpoint
   - review the planned public contract, provider policy, telemetry schema, and
     fallback behavior with the human before implementation starts
3. Implement
   - add the public `horadus tasks ...` command surface
   - add thin provider adapters and normalized error/reporting behavior
   - update Make/docs/skill/reference surfaces that route users to the command
4. Validate
   - run focused provider/workflow tests, unaffected-caller regression coverage,
     and the canonical local gate
5. Ship (PR, checks, merge, main sync)
   - complete the human-gated review/sign-off path before merge

## Decisions (Timestamped)

- 2026-03-15: Make the public workflow contract provider-neutral and treat
  Codex CLI, Claude Code, and Gemini CLI as the initial supported adapters.
  (reason: local probing shows the CLIs do not share one native review-command
  interface)
- 2026-03-15: Keep optional custom review instructions in the repo-owned
  contract instead of exposing provider-specific prompt flags. (reason: Codex
  has dedicated review commands while Claude Code and Gemini rely on promptable
  headless execution)
- 2026-03-15: Store machine-readable review telemetry and optional raw outputs
  only under gitignored `artifacts/agent/local-review/` paths inside the repo,
  not in tracked source paths or ad hoc repo-root files. (reason: the repo
  already uses `artifacts/agent/` for local non-source-of-truth artifacts, and
  gitignored paths avoid polluting task diffs while keeping outputs
  discoverable)
- 2026-03-15: Use `HORADUS_LOCAL_REVIEW_PROVIDER` from `.env.harness` as the
  configurable default provider, but let explicit CLI selection override it and
  default to `claude` when no override is set. (reason: users want a stable
  repo-local default while still allowing agents or operators to choose another
  supported CLI for a specific run)
- 2026-03-15: Keep `.env.harness` optional and local-only, not a versioned
  source-of-truth file. (reason: workstation-specific provider defaults belong
  in local config, not committed repo state)
- 2026-03-15: Keep local review opt-in for now and add lightweight usefulness
  tracking instead of making it an immediate workflow gate. (reason: the repo
  should measure value before requiring a cross-provider local review step on
  every task)
- 2026-03-15: Auto-fallback is allowed only when a provider CLI is missing on
  `PATH`; other failure classes require explicit
  `--allow-provider-fallback`. (reason: a missing binary is a simple local
  availability problem, while auth/config/runtime failures should stay visible
  by default)
- 2026-03-15: Use a deterministic fallback order for non-explicit-provider
  runs, starting from the resolved env/default provider and then trying the
  remaining supported providers in repo order `claude` -> `codex` -> `gemini`,
  skipping providers already attempted. (reason: fallback behavior should be
  predictable and testable rather than opportunistic)
- 2026-03-15: Store local-review telemetry in gitignored artifacts under
  `artifacts/agent/local-review/`, using append-only JSONL plus optional per-run
  raw outputs. (reason: the repo already treats `artifacts/agent/` as local
  non-source-of-truth storage, and review logs should not pollute the branch
  diff)
- 2026-03-15: Make structured stdout, not the append-only JSONL artifact, the
  primary machine-consumption surface for agents. (reason: agents need a
  single per-run result without parsing stateful logs or provider-specific raw
  output)
- 2026-03-15: Treat findings as a successful review outcome rather than a
  command failure. (reason: this step is explicitly opt-in and advisory in this
  task, so findings belong in structured output/telemetry instead of a failing
  process exit code)

## Risks / Foot-guns

- Over-abstracting the provider seam could hide concrete CLI limitations -> keep
  the adapter surface limited to diff selection, instructions, and output
  capture
- Provider CLI behavior can drift independently -> document current assumptions
  in one canonical place and back them with adapter-specific regression tests
- A missing or stale `.env.harness` setting could hide which provider is in use
  -> print the resolved provider and selection source in command output/tests
- Treating `.env.harness` as local config without keeping it untracked would
  leak workstation state into the repo -> keep the ignore/update path explicit
- If usefulness tracking is too vague, the repo will not learn whether the step
  helps -> keep the tracked fields narrow and actionable from the first version
- Auto-fallback on auth/config/runtime failures would blur root cause and value
  measurement -> keep those failures visible unless
  `--allow-provider-fallback` is explicitly set
- A non-deterministic fallback order would make the command hard to reason
  about and test -> document one stable provider order and log which provider
  was attempted versus which provider actually ran
- Raw review output can become noisy or accidentally influence follow-on diffs
  -> keep the canonical telemetry append-only/minimal and store any retained raw
  output only in the dedicated gitignored run directory
- If agents must parse append-only telemetry to get the latest result, the
  interface becomes stateful and brittle -> keep machine consumption on
  structured stdout and reserve JSONL for history/audit
- If findings flip the process to non-zero exit codes, callers may mistake an
  advisory review for a workflow failure -> keep findings on the success path
  and reserve non-zero exits for actual invocation/provider problems
- Prompt-only providers may produce less structured output than dedicated review
  commands -> normalize prompts/output handling explicitly and fail clearly when
  a provider cannot satisfy the requested mode
- Planning on a non-sprint task can drift from the executable workflow -> keep
  the current blocker explicit and re-run eligibility after any sprint update

## Telemetry Fields

- `timestamp`
- `task_id` when known from branch or explicit input
- `executed_provider`
- `provider_source` (`cli`, `env`, or `default`)
- `attempted_provider`
- `fallback_provider` when a second provider is used
- `review_target_kind` (`base`, `uncommitted`, or `commit`)
- `review_target_value`
- `instructions_supplied`
- `outcome` (`ok`, `blocked`, or `failed`)
- `duration_ms`
- `findings_reported`
- `usefulness_outcome` (`changed_code`, `changed_docs`, `changed_tests`,
  `no_change`, `not_useful`, or `unknown`)
- `raw_output_path` when a per-run raw artifact is retained

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks eligibility TASK-286`
- `uv run --no-sync horadus tasks safe-start TASK-286 --name cli-agnostic-local-review`
- `uv run --no-sync pytest tests/unit/ tests/workflow/ -q`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Caller inventory:
  - `horadus` task CLI entrypoints in `tools/horadus/python/horadus_cli/`
  - shared workflow helpers in `tools/horadus/python/horadus_workflow/`
  - compatibility wrapper(s) in `Makefile`
  - agent-facing guidance in `docs/AGENT_RUNBOOK.md`
  - command guidance in `ops/skills/horadus-cli/SKILL.md` and
    `ops/skills/horadus-cli/references/commands.md`
  - workflow/CLI regression tests under `tests/unit/` and `tests/workflow/`
- Local interface notes:
  - `codex`: dedicated `review` plus promptable `exec`
  - `claude`: promptable headless `--print`
  - `gemini`: promptable headless `--prompt`
