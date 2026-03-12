# TASK-305: Let Guarded Task Start Carry Target Planning Intake Files

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: Done
- Planning Gates: Not Required — targeted workflow eligibility fix on existing guarded task-start behavior

## Goal (1-3 lines)

Allow the shared guarded task-start flow behind
`horadus tasks start/safe-start TASK-XXX --name short-name` to carry forward
task-scoped planning intake cleanly, including untracked target exec plan/spec
files, without weakening the repo’s normal dirty-tree protection.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-305`)
  - canonical task-start policy in `AGENTS.md`
  - command/operator guidance in `docs/AGENT_RUNBOOK.md`
- Runtime/code touchpoints:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/task_repo.py`
  - `src/horadus_cli/v2/task_commands.py`
  - `scripts/check_agent_task_eligibility.sh`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/unit/scripts/test_check_agent_task_eligibility.py`
  - `tests/workflow/`
- Preconditions/dependencies:
  - preserve the current guarded task-start semantics for non-planning dirt
  - preserve sprint-eligibility and sequencing enforcement
  - preserve task-scoped intake only; do not broaden carry-forward to arbitrary files

## Outputs

- Expected behavior/artifacts:
  - the shared guarded `start` / `safe-start` path treats shared live task ledgers as eligible carry-forward only when they are task-intake edits
  - the same guarded `start` / `safe-start` path also treats target-task planning artifacts as eligible carry-forward even when they are untracked:
    - `tasks/exec_plans/TASK-XXX.md`
    - task-owned spec files under `tasks/specs/` that belong to `TASK-XXX`
  - untracked planning artifacts are attributed to the requested task by exact path/task-id ownership, not by diff-based task refs:
    - `tasks/exec_plans/TASK-XXX.md` -> `task_id_from_exec_plan_path(...)` ownership match
    - `tasks/specs/<task-num>-*.md` -> `task_id_from_spec_path(...)` ownership match
  - ineligible dirty/untracked files still block task start
  - command output clearly separates:
    - eligible carry-forward files
    - blocking files
  - docs describe the exact intake eligibility rule, including the untracked target exec-plan/spec case
- Validation evidence:
  - regression coverage for eligible untracked target planning artifacts
  - regression coverage for blocked unrelated dirty/untracked files
  - canonical start commands in docs remain aligned to actual CLI behavior

## Non-Goals

- Explicitly excluded work:
  - allowing arbitrary docs/code/test files to carry forward
  - weakening the clean-main / no-open-task-PR preflight rules
  - changing task-close or finish semantics
  - redesigning planning gates or planning artifact templates

## Scope

- In scope:
  - define the exact eligible planning-intake file set for guarded task start
  - include untracked target-task planning artifacts in that set
  - keep the lower-level `horadus tasks start` behavior aligned with `safe-start` because both share the same guarded preflight
  - keep unrelated dirty/untracked files blocking
  - keep command output explicit about what was carried vs blocked
  - update task-start docs to match the final eligibility rule
- Out of scope:
  - repo-wide dirty-tree exceptions
  - non-task workflow commands
  - changing branch naming, PR metadata, or finish policy

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: whitelist only shared live task ledgers plus planning artifacts that belong to the requested task id
- Accepted ownership proof for untracked artifacts: `task_id_from_exec_plan_path(...)` for exec plans and `task_id_from_spec_path(...)` for specs; do not rely on git diff attribution for brand-new files
- Rejected simpler alternative: allow any file under `tasks/` to carry forward; too broad and likely to hide unrelated planning drift
- Rejected riskier alternative: allow any untracked file during `safe-start`; this would defeat the guarded-start value
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory every current caller of the shared guarded start/preflight behavior before changing shared workflow behavior, including:
     - `horadus tasks start`
     - `horadus tasks safe-start`
     - `scripts/check_agent_task_eligibility.sh`
     - `tests/unit/scripts/test_check_agent_task_eligibility.py`
   - identify the current eligibility logic for:
     - shared live ledgers (`tasks/BACKLOG.md`, `tasks/CURRENT_SPRINT.md`)
     - tracked target-task planning artifacts
     - untracked target-task planning artifacts
   - define the exact target-task planning artifact patterns that are eligible:
     - `tasks/exec_plans/TASK-XXX.md`
     - task-owned `tasks/specs/` files for `TASK-XXX`
   - define the ownership proof for untracked planning artifacts before editing the intake gate:
     - `task_id_from_exec_plan_path(...)` ownership for exec-plan files
     - `task_id_from_spec_path(...)` ownership for spec files
   - inventory unaffected callers that must stay green after the change

2. Implement
   - update guarded-start eligibility logic to recognize untracked target-task planning artifacts as eligible carry-forward
   - keep the shared `task_preflight_data()` contract aligned for both `horadus tasks start` and `horadus tasks safe-start`
   - implement untracked artifact ownership checks without relying on diff-based task refs
   - preserve blocking behavior for:
     - unrelated task specs/exec plans
     - non-task docs
     - code/tests/runtime files
   - keep output explicit about eligible vs blocking files
   - update docs in `AGENTS.md` / `docs/AGENT_RUNBOOK.md` only if wording must change to match the final behavior

3. Validate
   - add regression coverage for:
     - eligible untracked `tasks/exec_plans/TASK-XXX.md`
     - eligible task-owned spec for `TASK-XXX`
     - blocked unrelated exec plan/spec
     - blocked unrelated non-task file
   - add at least one unaffected-caller regression, per shared-workflow guardrail:
     - `tests/unit/scripts/test_check_agent_task_eligibility.py`
   - rerun relevant workflow tests plus the guarded-start CLI surface

4. Ship (PR, checks, merge, main sync)
   - run the canonical local gate
   - close task ledgers on-branch
   - open ready PR with canonical metadata
   - complete merge through `horadus tasks finish TASK-305`

## Decisions (Timestamped)

- 2026-03-12: Keep the dirty-tree exception narrow and task-scoped; the fix is to recognize untracked target planning artifacts, not to relax guarded start broadly

## Risks / Foot-guns

- Over-broad eligibility can hide unrelated work in the new task branch -> whitelist by exact path/task-id ownership only
- Under-broad eligibility can keep blocking normal planning intake -> test both tracked and untracked target artifact cases
- Diff-only ownership checks will still reject brand-new target planning files -> move untracked artifact ownership onto path/task-id matching
- Output that does not distinguish eligible vs blocking files will make start failures hard to debug -> preserve explicit reporting
- Shared workflow change can break unrelated start/preflight callers -> add at least one unaffected-caller regression

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_cli.py -k "safe_start or preflight" -q`
- `uv run --no-sync pytest tests/workflow -q -k "safe_start or preflight or task_start"`
- `uv run --no-sync pytest tests/unit/scripts/test_check_agent_task_eligibility.py -q`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `tools/horadus/python/horadus_workflow/task_workflow_core.py`
  - `tools/horadus/python/horadus_workflow/task_repo.py`
  - `src/horadus_cli/v2/task_commands.py`
  - `scripts/check_agent_task_eligibility.sh`
  - `tests/horadus_cli/v2/test_cli.py`
  - `tests/unit/scripts/test_check_agent_task_eligibility.py`
  - `docs/AGENT_RUNBOOK.md`
  - `AGENTS.md`
