# TASK-297 Compatibility Baseline

This file is the checked-in compatibility artifact for `TASK-297`.

Maintain it during implementation and review. It is the source of truth for:
- command/subcommand/flag compatibility scope
- command-to-scenario coverage links
- caller/import inventory for extracted symbol groups
- fallback-sensitive baseline scenarios
- dependency/ownership boundaries for the refactor

## Artifact Completion Rules

- Populate this file before the first extraction commit.
- Every command row must include:
  - current symbol group(s)
  - planned owner
  - caller/import ids
  - validating scenario ids, or explicit `N/A` with rationale
- Every caller/import row must map to one or more command ids or be marked
  `internal-only`.
- Every fallback-sensitive scenario must declare:
  - expected exit code
  - primary output stream
  - fallback expectation (`none`, `allowed`, or `forced`)
  - friction-record expectation
  - recovery hint expectation
- No extraction phase is complete until every touched command row is backed by
  a validating scenario run or an explicit unchanged-by-construction note in
  the implementation PR.

## Dependency / Ownership Map

### Allowed dependency direction

- `task_commands.py` -> `task_workflow.py` and single-domain modules
- `task_workflow.py` -> single-domain modules
- single-domain modules -> `task_process.py`, `task_shared.py`, `task_repo.py`
- single-domain modules must not depend on each other directly

### Ownership rules

- `task_commands.py`
  - argparse registration
  - trivial argument normalization / handler dispatch only
  - no workflow policy branching, subprocess orchestration, repo mutation, or
    cross-domain command composition
- `task_workflow.py` (or explicitly named equivalent)
  - owner of cross-domain command composition
  - owner of flows that need to sequence multiple workflow domains in one
    command path
  - must not become a generic utility module
- `task_repo.py`
  - read-side path resolution and parsing for task/backlog/archive data
  - no workflow orchestration or write-side ledger mutation
- `task_ledgers.py`
  - write-side sprint/backlog/completed/archive mutation concerns
- `task_shared.py` (or equivalent)
  - shared dataclasses, exceptions, config/result envelopes, and helper types
    used by 2+ workflow domains
  - no workflow logic or repo I/O

## Command Compatibility Inventory

| ID | Command / variants | Current symbol group(s) | Planned owner | Caller/import ids | Scenario ids | Compatibility contract |
| --- | --- | --- | --- | --- | --- | --- |
| CMD-01 | `list-active` | `handle_list_active` | `task_query.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-01` | Preserve current sprint read path, output format support, and exit code semantics. |
| CMD-02 | `show TASK-ID`; `show TASK-ID --include-archive` | `handle_show` | `task_query.py` | `CALL-01`, `CALL-03`, `CALL-05`, `CALL-06` | `SCN-10`, `SCN-11` | Preserve task-id normalization, live-first lookup, archive opt-in gate, not-found behavior, and stdout/stderr routing. |
| CMD-03 | `search QUERY...`; `--status`; `--limit`; `--include-raw`; `--include-archive` | `handle_search` | `task_query.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-12`, `SCN-13` | Preserve live-only default search scope, archive opt-in behavior, filter semantics, and raw-block inclusion contract. |
| CMD-04 | `context-pack TASK-ID`; `context-pack TASK-ID --include-archive` | `handle_context_pack` | `task_query.py` | `CALL-01`, `CALL-03`, `CALL-06` | `SCN-14`, `SCN-15` | Preserve context assembly order, live-first lookup, archive opt-in behavior, and not-found messaging. |
| CMD-05 | `preflight` | `task_preflight_data`, `handle_preflight` | `task_preflight.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-02`, `SCN-03` | Preserve sequencing guard behavior, clean-main success contract, blocker classification, and recovery hints. |
| CMD-06 | `eligibility TASK-ID` | `eligibility_data`, `handle_eligibility` | `task_preflight.py` | `CALL-01`, `CALL-03` | `SCN-04` | Preserve autonomous-start eligibility checks, blocker classes, and task-id validation behavior. |
| CMD-07 | `start TASK-ID --name NAME` | `start_task_data`, `handle_start` | `task_preflight.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-05` | Preserve branch naming/creation rules, preflight dependency, and failure classification. |
| CMD-08 | `safe-start TASK-ID --name NAME` | `safe_start_task_data`, `handle_safe_start` | `task_workflow.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-06`, `SCN-07` | Preserve composed eligibility-plus-start behavior, task-ledger-only dirtiness allowance, and unrelated-dirtiness blocker contract. |
| CMD-09 | `close-ledgers TASK-ID` | `close_ledgers_task_data`, `handle_close_ledgers` | `task_ledgers.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-08`, `SCN-09` | Preserve archive append, live-ledger removal/update semantics, and task-not-found behavior. |
| CMD-10 | `record-friction TASK-ID --command-attempted ... --fallback-used ... --friction-type ... --note ... --suggested-improvement ...` | `record_friction_data`, `handle_record_friction` | `task_friction.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-16` | Preserve validation requirements, artifact path behavior, and structured entry emission. |
| CMD-11 | `summarize-friction`; `--date`; `--output` | `summarize_friction_data`, `handle_summarize_friction` | `task_friction.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-17` | Preserve report generation defaults, date validation, output-path override behavior, and environment error handling. |
| CMD-12 | `finish`; `finish TASK-ID` | `FinishConfig`, `finish_task_data`, `handle_finish` | `task_finish.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-18`, `SCN-19`, `SCN-20`, `SCN-21` | Preserve review-gate wait rules, merged-PR convergence, closure invariant enforcement, and local-main sync verification. |
| CMD-13 | `lifecycle`; `lifecycle TASK-ID`; `--strict` | `task_lifecycle_data`, `handle_lifecycle` | `task_lifecycle.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-22`, `SCN-23` | Preserve lifecycle snapshot fields, strict verifier semantics, and incomplete-closure failure classification. |
| CMD-14 | `local-gate`; `--full` | `local_gate_data`, `handle_local_gate` | `task_workflow.py` | `CALL-01`, `CALL-03`, `CALL-05` | `SCN-24`, `SCN-25` | Preserve default vs full gate behavior, dry-run guardrails, and environment failure classification. |

## Current Symbol-Group Extraction Map

| Group ID | Current symbols in `task_commands.py` | Planned home | Covered command ids | Notes |
| --- | --- | --- | --- | --- |
| SYM-01 | `handle_list_active`, `handle_show`, `handle_search`, `handle_context_pack` | `task_query.py` | `CMD-01`, `CMD-02`, `CMD-03`, `CMD-04` | Read-oriented query handlers should stay close to `task_repo.py` without owning repo parsing. |
| SYM-02 | `task_preflight_data`, `eligibility_data`, `start_task_data`, `handle_preflight`, `handle_eligibility`, `handle_start` | `task_preflight.py` | `CMD-05`, `CMD-06`, `CMD-07` | Single-domain start/preflight policy helpers stay together. |
| SYM-03 | `safe_start_task_data`, `handle_safe_start`, cross-domain start sequencing helpers | `task_workflow.py` | `CMD-08` | `safe-start` composes eligibility and start behavior, so it is owned by the orchestration layer. |
| SYM-04 | `close_ledgers_task_data`, `handle_close_ledgers` | `task_ledgers.py` | `CMD-09` | Owns write-side backlog/current-sprint/completed/archive updates. |
| SYM-05 | `record_friction_data`, `summarize_friction_data`, `handle_record_friction`, `handle_summarize_friction` | `task_friction.py` | `CMD-10`, `CMD-11` | Artifact-only feedback helpers remain isolated from core workflow orchestration. |
| SYM-06 | `FinishConfig`, `finish_task_data`, `handle_finish`, finish-specific review/merge helpers | `task_finish.py` | `CMD-12` | Finish flow remains its own domain because it owns review-gate and merge-specific policy. |
| SYM-07 | `task_lifecycle_data`, `handle_lifecycle`, strict lifecycle/closure helpers | `task_lifecycle.py` | `CMD-13` | Lifecycle reads and strict verification stay isolated from merge logic. |
| SYM-08 | `local_gate_data`, `handle_local_gate`, multi-step validation orchestration helpers | `task_workflow.py` | `CMD-14` | `local-gate` sequences multiple checks and is therefore cross-domain orchestration. |
| SYM-09 | subprocess runners, timeout helpers, shell execution helpers | `task_process.py` | `internal-only` | No direct CLI command ownership; consumed by multiple domains. |
| SYM-10 | shared dataclasses, config/result envelopes, helper types, normalized workflow exceptions | `task_shared.py` | `internal-only` | Must not absorb workflow logic or repo access. |

## Caller / Import Inventory

| Caller ID | Consumer | Relationship | Covered command ids | Notes |
| --- | --- | --- | --- | --- |
| CALL-01 | `src/horadus_cli/task_commands.py` | CLI facade dispatches every `handle_*` entrypoint and parser wiring must remain stable | `CMD-01` to `CMD-14` | Direct owner of argparse registration and final `CommandResult` emission only. |
| CALL-02 | `src/horadus_cli/app.py` | Loads `register_task_commands` and relies on stable subcommand registration | `CMD-01` to `CMD-14` | Keep parser registration stable at the CLI root. |
| CALL-03 | `tests/horadus_cli/v1/test_cli.py` | CLI contract coverage for parser, render, exit-code, and handler integration paths | `CMD-01` to `CMD-14` | Must continue to cover unaffected commands after each phase. |
| CALL-04 | `tests/unit/scripts/` | Script-level workflow regression coverage for task-related commands | `CMD-03`, `CMD-04`, `CMD-12`, `CMD-13`, `CMD-14` | Narrow further into concrete test files during implementation. |
| CALL-05 | `docs/AGENT_RUNBOOK.md`, `README.md`, `AGENTS.md` | Operator-facing docs depend on command names, flags, and recovery guidance remaining stable | `CMD-01` to `CMD-14` | Update only if module-ownership guidance changes, not for internal reshuffling. |
| CALL-06 | Archive/task-query tests and fixtures under `tests/unit/scripts/` and related task-repo fixtures | Cover live/archive lookup behavior for `show` and `context-pack` | `CMD-02`, `CMD-04` | Keep archive opt-in semantics explicit and regression-tested. |

## Fallback-Sensitive Baseline Scenarios

| Scenario ID | Command / args | Preconditions | Expected class | Exit code | Primary stream | Fallback expectation | Friction expectation | Recovery hint expectation | Covered commands |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SCN-01 | `horadus tasks list-active` | Current sprint exists and includes open tasks | success | `0` | stdout | `none` | `none` | none required | `CMD-01` |
| SCN-02 | `horadus tasks preflight` | On clean, synced `main` with no open conflicting task PR | success | `0` | stdout | `none` | `none` | none required | `CMD-05` |
| SCN-03 | `horadus tasks preflight` | Dirty tree or unsynced `main` blocks task start | validation blocker | `2` or `4` depending on root cause | stderr | `none` | `none` | must hint at the blocking repo-state fix | `CMD-05` |
| SCN-04 | `horadus tasks eligibility TASK-XXX` | Task id invalid, blocked, or not in current sprint/autonomous-eligible set | validation blocker | `2` | stderr | `none` | `none` | must explain why autonomous start is blocked | `CMD-06` |
| SCN-05 | `horadus tasks start TASK-XXX --name short-name` | Preflight passes and task branch can be created | success | `0` | stdout | `none` | `none` | none required | `CMD-07` |
| SCN-06 | `horadus tasks safe-start TASK-XXX --name short-name` | Only task-ledger intake files are dirty and task is eligible | success | `0` | stdout | `none` | `none` | none required | `CMD-08` |
| SCN-07 | `horadus tasks safe-start TASK-XXX --name short-name` | Unrelated dirty files exist or sequencing guard fails | validation blocker | `2` | stderr | `none` | `none` | must identify the exact blocking dirtiness/guard condition | `CMD-08` |
| SCN-08 | `horadus tasks close-ledgers TASK-XXX` | Live task exists and is closable | success | `0` | stdout | `none` | `none` | none required | `CMD-09` |
| SCN-09 | `horadus tasks close-ledgers TASK-XXX` | Task missing from live ledgers | not found | `3` | stderr | `none` | `none` | must report missing live task record | `CMD-09` |
| SCN-10 | `horadus tasks show TASK-XXX` | Task exists in live backlog/current sprint | success | `0` | stdout | `none` | `none` | none required | `CMD-02` |
| SCN-11 | `horadus tasks show TASK-XXX --include-archive` | Task no longer live but exists in archive | success | `0` | stdout | `none` | `none` | if archive flag absent, must hint to retry with `--include-archive` | `CMD-02` |
| SCN-12 | `horadus tasks search words` | Live backlog contains matches | success | `0` | stdout | `none` | `none` | none required | `CMD-03` |
| SCN-13 | `horadus tasks search words --include-archive --status completed --include-raw` | Match exists only in archive/completed records | success | `0` | stdout | `none` | `none` | default behavior must remain live-only unless archive flag is present | `CMD-03` |
| SCN-14 | `horadus tasks context-pack TASK-XXX` | Task exists live with backlog/spec/sprint context | success | `0` | stdout | `none` | `none` | none required | `CMD-04` |
| SCN-15 | `horadus tasks context-pack TASK-XXX --include-archive` | Task exists only in archive | success | `0` | stdout | `none` | `none` | missing-live path must hint to `--include-archive` when appropriate | `CMD-04` |
| SCN-16 | `horadus tasks record-friction ...` | Required args valid and artifact directory writable | success | `0` | stdout | `none` | `n/a` | none required | `CMD-10` |
| SCN-17 | `horadus tasks summarize-friction --date YYYY-MM-DD` | Friction artifacts readable; optional output path omitted | success | `0` | stdout | `none` | `n/a` | report path/default location should remain discoverable | `CMD-11` |
| SCN-18 | `horadus tasks finish TASK-XXX` | PR is ready, checks green, review gate passes, merge proceeds | success | `0` | stdout | `none` | `none` | none required | `CMD-12` |
| SCN-19 | `horadus tasks finish TASK-XXX` | Actionable current-head review comment or unresolved blocking thread exists | environment or validation blocker | `2` or `4` depending on source | stderr | `none` | `none` | must report review-gate blocker and requested next step | `CMD-12` |
| SCN-20 | `horadus tasks finish TASK-XXX` | PR already merged before rerun; local repo still needs converge-to-main path | success | `0` | stdout | `none` | `none` | none required | `CMD-12` |
| SCN-21 | `horadus tasks finish TASK-XXX` | Closure invariant fails (task still live, missing completed/archive state, or local main unsynced) | validation blocker | `2` | stderr | `none` | `none` | must name the exact missing closure step | `CMD-12` |
| SCN-22 | `horadus tasks lifecycle TASK-XXX` | Task branch or task id resolves and state is inspectable | success | `0` | stdout | `none` | `none` | none required | `CMD-13` |
| SCN-23 | `horadus tasks lifecycle TASK-XXX --strict` | Task is not fully complete by repo policy | validation blocker | `2` | stderr | `none` | `none` | must identify the missing completion invariant(s) | `CMD-13` |
| SCN-24 | `horadus tasks local-gate` | Default local validation succeeds | success | `0` | stdout | `none` | `none` | none required | `CMD-14` |
| SCN-25 | `horadus tasks local-gate --full` | Full CI-parity path encounters failing gate | environment blocker | `4` | stderr | `none` | `none` | must identify the failing gate command or check | `CMD-14` |
| SCN-26 | `horadus tasks --help` | CLI loads parser tree successfully | success | `0` | stdout | `none` | `none` | none required | `CMD-01` to `CMD-14` |
| SCN-27 | `horadus tasks start TASK-XXX` | Required `--name` flag omitted so argparse handles the failure | validation blocker | `2` | stderr | `none` | `none` | usage text and missing-argument cue must remain visible | `CMD-07` |

## Observable CLI Contract Notes

Compatibility is not byte-for-byte text identity. Preserve:
- command names and supported options
- JSON field contracts where applicable
- exit codes from `src/horadus_cli/result.py`:
  - `0` = success
  - `2` = validation error
  - `3` = not found
  - `4` = environment error
- stdout vs stderr routing expectations
- blocker/success class semantics
- required recovery guidance and hinted commands
- `--help` reachability and option discoverability

## Review Checklist

- Every command exposed by `uv run --no-sync horadus tasks --help` appears in
  the command inventory.
- Every current symbol group extracted from `task_commands.py` appears in the
  symbol-group map.
- Every caller/import row maps to concrete command ids or `internal-only`.
- Every command row maps to at least one scenario id or explicit `N/A`.
- Every scenario row records fallback and recovery expectations, even when the
  value is `none`.
- Root help reachability and at least one argparse failure path stay covered by
  explicit scenarios, not just prose notes.
