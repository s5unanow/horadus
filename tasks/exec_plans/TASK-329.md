# TASK-329: Right-Size `AGENTS.md` Around Policy Invariants and Thin Helper Surfaces

## Status

- Owner: Codex
- Started: 2026-03-14
- Current state: In progress
- Planning Gates: Required — shared workflow-policy surface, helper-skill routing, and docs-freshness drift checks

## Goal (1-3 lines)

Trim `AGENTS.md` without reversing the repo's current design that makes it the
sole workflow-policy owner. Keep only always-on policy in `AGENTS.md`, route
optional command/playbook detail to thin helper surfaces, and decide whether a
repo-workflow skill is worth adding or reviving as a thin aid.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-329`, `TASK-254`, `TASK-267`)
  - `tasks/exec_plans/TASK-308.md`
  - `tasks/exec_plans/TASK-304.md`
- Runtime/code touchpoints:
  - `AGENTS.md`
  - `README.md`
  - `docs/AGENT_RUNBOOK.md`
  - `ops/skills/horadus-cli/SKILL.md`
  - `ops/skills/horadus-cli/references/commands.md`
  - `ops/skills/repo-workflow/SKILL.md`
  - `ops/skills/repo-workflow/references/`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tests/workflow/`
  - `tests/horadus_cli/v2/test_task_query.py`
- Caller inventory for shared workflow-policy helpers/config:
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_query.py`
  - `tests/workflow/test_repo_workflow.py`
  - `tests/workflow/test_task_workflow.py`
  - `tests/workflow/test_docs_freshness.py`
  - `tests/horadus_cli/v2/test_task_query.py`
- Preconditions/dependencies:
  - preserve `AGENTS.md` as the only canonical workflow-policy owner
  - avoid creating a second standalone workflow spec in a skill or runbook
  - repo-local skills are not guaranteed to be installed in every agent runtime; the workflow must remain safe without them
  - resolve whether `TASK-254` and `TASK-267` are revived, superseded, partially subsumed, or left untouched with explicit rationale

## Outputs

- Expected behavior/artifacts:
  - a section-by-section policy-surface inventory for `AGENTS.md`
  - a slimmer `AGENTS.md` that keeps hard policy and removes helper/reference detail
  - thin helper surfaces (`README.md`, `docs/AGENT_RUNBOOK.md`, Horadus skill/command notes, optional repo-workflow skill) that point back to canonical policy instead of duplicating it
  - any optional skill helper remains additive rather than a hidden prerequisite for normal repo workflow execution
  - workflow reference providers plus drift-check coverage that enforce the chosen ownership boundaries, including any new thin workflow-skill surface if one is created
- Validation evidence:
  - targeted docs-freshness / workflow-drift checks
  - representative grep checks showing canonical workflow-policy phrases remain only in `AGENTS.md`
  - targeted workflow tests if helper generation or drift-check logic changes

## Non-Goals

- Explicitly excluded work:
  - moving canonical workflow policy out of `AGENTS.md`
  - turning skills into a mandatory runtime dependency for normal task execution
  - redesigning unrelated product/project documentation
  - broad Horadus CLI behavior changes unrelated to documentation/skill ownership

## Scope

- In scope:
  - classify `AGENTS.md` sections into keep / compress / move buckets
  - trim command-index, orientation, and volatile recovery-playbook detail out of `AGENTS.md` where safe
  - decide whether a thin repo-workflow skill is needed beyond the existing Horadus CLI skill
  - keep `context-pack` workflow/navigation output aligned with any ownership changes to shared workflow reference providers
  - update helper surfaces and drift checks to match the new ownership split
  - reconcile overlap with `TASK-254` and `TASK-267`
- Out of scope:
  - changing workflow semantics themselves
  - replacing `horadus` with shell scripts or ad hoc markdown parsing
  - adding broad new agent-doc surfaces that restate the same policy in parallel

## Inventory (Keep / Compress / Move)

- Keep in `AGENTS.md`:
  - source-of-truth hierarchy
  - code-shape and workflow guardrails
  - human-gated rules
  - task branching / completion policy
  - git conventions that affect task lifecycle execution
- Compress in `AGENTS.md`:
  - project description
  - working-agreement prose
  - high-level repo routing
- Move to thin helper/reference surfaces:
  - repo navigation and setup pointers -> `README.md`
  - command index / operator notes -> `docs/AGENT_RUNBOOK.md`
  - Horadus command helper wording -> `ops/skills/horadus-cli/`
- Do not add right now:
  - `ops/skills/repo-workflow/`; the existing runbook plus Horadus CLI skill cover the thin-helper role without adding a second workflow surface

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: `AGENTS.md` stays authoritative for hard workflow policy; helper docs/skills stay thin and command-oriented
- Rejected simpler alternative: move policy detail back into the runbook or skill surfaces and rely on cross-links; that reopens the drift problem solved by `TASK-304` / `TASK-308`
- First integration proof: `TASK-304` and `TASK-308` already established the "thin outside AGENTS" baseline to preserve
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - run:
     - `uv run --no-sync horadus tasks preflight`
     - `uv run --no-sync horadus tasks safe-start TASK-329 --name trim-agents-policy-surface`
     - `uv run --no-sync horadus tasks context-pack TASK-329`
   - inventory the current `AGENTS.md` sections and mark each as keep / compress / move
   - inventory the current helper surfaces and existing drift-check coverage
   - decide how `TASK-254` and `TASK-267` should interact with this task before implementation starts

2. Implement
   - trim `AGENTS.md` down to hard policy and short invariant summaries
   - move command/reference material to existing thin helper surfaces (`README.md`, runbook, Horadus skill, command notes) only when that move does not create a second policy owner
   - add or revive a thin repo-workflow skill only if it meaningfully reduces optional playbook detail
   - update workflow reference providers and docs-freshness checks to reflect the chosen ownership boundaries
   - if a repo-workflow skill is added, register it in the thin-surface enforcement set and extend regression coverage so policy duplication there fails closed

3. Validate
   - verify the targeted canonical policy phrases still live in `AGENTS.md`
   - verify thin helper surfaces do not reintroduce forbidden policy markers
   - run docs-freshness and targeted workflow tests
   - run targeted `context-pack`/query tests if shared workflow reference providers or navigation surfaces change

4. Ship (PR, checks, merge, main sync)
   - close `TASK-329` in live ledgers on the PR head
   - run required local gates
   - push, open/update the PR, address review, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-14: Treat the work as an `AGENTS.md` trimming task, not a reversal of `TASK-308`; `AGENTS.md` remains the only workflow-policy owner.
- 2026-03-14: Evaluate skills only as thin helper surfaces for optional playbooks, not as replacements for root policy.
- 2026-03-14: Treat repo-local skills as optional aids because they may not be installed in the active agent runtime.
- 2026-03-14: Reconcile agent-navigation work (`TASK-254`) separately from policy-trimming work unless a smaller combined change is clearly cleaner.
- 2026-03-14: Use `README.md` plus `docs/AGENT_RUNBOOK.md` as the thin navigation/index layer so `TASK-254` only needs follow-up work if a separate navigation gap remains.
- 2026-03-14: Do not add a repo-workflow skill in this task; defer `TASK-267` unless the existing runbook plus Horadus CLI skill prove insufficient.

## Risks / Foot-guns

- Over-trimming removes policy agents actually need at runtime -> keep invariant summaries in `AGENTS.md` even when longer detail moves out
- Adding a repo-workflow skill creates a second workflow spec -> keep the skill thin and route it back to `AGENTS.md` / `horadus`
- A helper skill silently becomes required in environments where it is not installed -> keep the canonical workflow executable and understandable without any repo-local skill
- Moved guidance lands in an untracked helper surface and escapes canonical reference providers -> limit destination surfaces to tracked thin helpers and update `repo_workflow.py` / `task_workflow_policy.py` together
- Drift checks focus on old marker phrases only -> refresh the checks alongside the new ownership split
- A newly added workflow skill is left outside thin-surface enforcement -> register it in docs-freshness and add regression coverage in the same task
- `TASK-254` / `TASK-267` overlap causes backlog confusion or duplicate doc work -> explicitly decide whether to reuse, supersede, or leave each separate before implementation
- Shared workflow reference-provider changes silently break `context-pack` output -> include `task_workflow_query.py` and targeted query tests in the same validation pass

## Validation Commands

- `uv run --no-sync python scripts/check_docs_freshness.py`
- `uv run --no-sync pytest tests/workflow -q -k "docs_freshness or repo_workflow"`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_query.py -q`
- `rg -n "THUMBS_UP|review-gate timeout|Do not claim a task is complete|safe-start TASK-" AGENTS.md`
- `rg -n "THUMBS_UP|review-gate timeout|Do not claim a task is complete|safe-start TASK-" README.md docs/AGENT_RUNBOOK.md ops/skills/horadus-cli/`
- `test ! -d ops/skills/repo-workflow || rg -n "THUMBS_UP|review-gate timeout|Do not claim a task is complete|safe-start TASK-" ops/skills/repo-workflow/`

## Notes / Links

- Spec:
  - backlog entry in `tasks/BACKLOG.md`
- Relevant modules:
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
  - `ops/skills/horadus-cli/SKILL.md`
  - `ops/skills/repo-workflow/`
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `tests/workflow/`
- Canonical examples:
  - `tasks/exec_plans/TASK-308.md`
  - `tasks/specs/275-finish-review-gate-timeout.md`
