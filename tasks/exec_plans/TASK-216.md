# TASK-216: Agent-Facing Horadus CLI Initiative

## Status

- Owner: Codex
- Started: 2026-03-06
- Current state: Done

## Goal (1-3 lines)

Turn `horadus` into the canonical structured interface for agent/operator repo
workflows, while keeping `make` and legacy scripts as thin compatibility
wrappers where appropriate.

## Scope

- In scope:
  - ADR for the CLI decision and boundaries
  - internal CLI package + shared output/exit-code model
  - task/sprint workflow commands
  - triage input collection command
  - wrapper/doc updates
  - repo-owned Codex skill and install/sync path
- Out of scope:
  - full migration of every shell script
  - MCP server/tooling
  - replacing PR/merge, backup, or Docker-heavy scripts in this pass

## Plan (Keep Updated)

1. Preflight (branch, tests, context) ✅
2. Implement ✅
3. Validate ✅
4. Ship (PR, checks, merge, main sync) ⏳

## Decisions (Timestamped)

- 2026-03-06: Keep public entrypoint `horadus`; use an internal package rather
  than a new top-level CLI product.
- 2026-03-06: Prioritize repo workflows and triage over broad runtime/admin
  command migration.
- 2026-03-06: Version the Codex skill in-repo under `ops/skills/horadus-cli`
  and install/sync it into `$CODEX_HOME/skills/horadus-cli`.

## Risks / Foot-guns

- Wrapper/CLI drift -> keep shell wrappers thin and CLI-owned.
- Agent breakage from output churn -> provide JSON mode for repo workflow
  commands and keep text output readable.
- Over-migrating shell-heavy flows -> defer PR/merge, Docker, and backup flows.

## Migration Inventory

### Migrate into CLI now

- task context pack
- task start sequencing preflight
- agent task eligibility
- task branch start
- backlog triage input collection

### Keep as `make` wrapper calling CLI

- `make task-preflight`
- `make agent-task-preflight`
- `make task-context-pack`
- `make task-start`
- `make agent-safe-start`
- `make doctor`

### Leave as shell/python script for now

- `scripts/finish_task_pr.sh`
- `scripts/enforce_main_protection.sh`
- `scripts/backup_postgres.sh`
- `scripts/restore_postgres.sh`
- `scripts/test_integration_docker.sh`
- `scripts/validate_assessment_artifacts.py`

### Deprecate later

- direct agent use of `scripts/task_context_pack.sh`
- direct agent use of `scripts/check_task_start_preflight.sh`
- direct agent use of `scripts/check_agent_task_eligibility.sh`
- direct agent use of `scripts/start_task_branch.sh`

## Validation Commands

- `python -m py_compile src/cli.py src/horadus_cli/*.py`
- `uv run --no-sync pytest tests/horadus_cli/v1/test_cli.py tests/unit/scripts/test_task_context_pack.py tests/unit/scripts/test_check_agent_task_eligibility.py -v -m unit`

## Notes / Links

- Spec: ADR-009
- Relevant modules:
  - `src/horadus_cli/`
  - `ops/skills/horadus-cli/`
