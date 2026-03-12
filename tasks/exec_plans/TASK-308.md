# TASK-308: Keep Workflow Guidance Thin Outside `AGENTS.md`

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: Done
- Planning Gates: Required — shared workflow docs, skill, and drift checks

## Goal (1-3 lines)

Keep `AGENTS.md` as the only workflow-policy owner while slimming `README.md`,
`docs/AGENT_RUNBOOK.md`, and the Horadus CLI skill surfaces down to narrow
overview, command-index, and procedural-helper roles.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-308`)
  - canonical workflow policy in `AGENTS.md`
- Runtime/code touchpoints:
  - `README.md`
  - `docs/AGENT_RUNBOOK.md`
  - `ops/skills/horadus-cli/SKILL.md`
  - `ops/skills/horadus-cli/references/commands.md`
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tests/workflow/`
- Preconditions/dependencies:
  - preserve `AGENTS.md` as the sole workflow-policy owner
  - keep operator- and agent-facing quick-reference surfaces usable after trimming

## Outputs

- Expected behavior/artifacts:
  - `README.md` is a narrow project overview / quick-start pointer surface
  - `docs/AGENT_RUNBOOK.md` is a thin command index with minimal operational reminders
  - Horadus CLI skill surfaces stay thin procedural helpers and command references
  - representative workflow-policy phrases live only in `AGENTS.md`
  - drift checks fail when the thinned surfaces reintroduce representative canonical policy blocks
- Validation evidence:
  - direct docs-freshness / workflow-drift checks over the affected surfaces
  - regression coverage for workflow policy helper generation where needed

## Non-Goals

- Explicitly excluded work:
  - changing workflow policy semantics themselves
  - redesigning unrelated project/product documentation
  - removing `README.md`, `docs/AGENT_RUNBOOK.md`, or the Horadus CLI skill entirely

## Scope

- In scope:
  - trim workflow-policy prose out of `README.md`
  - keep `docs/AGENT_RUNBOOK.md` thin and command-oriented
  - keep Horadus CLI skill surfaces thin and command-oriented
  - update workflow helper/policy text generation to match the thin-surface contract
  - extend drift checks so representative policy phrases outside `AGENTS.md` are caught
- Out of scope:
  - new workflow commands
  - unrelated README/product overview changes
  - non-workflow skill cleanup

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: keep `AGENTS.md` authoritative and reduce other surfaces to brief summaries plus links/pointers
- Rejected simpler alternative: allow each workflow-facing doc/surface to restate the policy “in its own words”; that reintroduces drift
- First integration proof: `TASK-304` already removed the worst workflow-policy duplication from the runbook and backlog
- Waivers: none

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - run canonical repo flow:
     - `uv run --no-sync horadus tasks preflight`
     - `uv run --no-sync horadus tasks safe-start TASK-308 --name thin-workflow-docs`
     - `uv run --no-sync horadus tasks context-pack TASK-308`
   - inventory representative workflow-policy phrases that must remain owner-only in `AGENTS.md`
   - inventory the surviving workflow guidance in:
     - `README.md`
     - `docs/AGENT_RUNBOOK.md`
     - `ops/skills/horadus-cli/SKILL.md`
     - `ops/skills/horadus-cli/references/commands.md`
   - inventory the workflow helper surfaces that currently emit or validate those phrases

2. Implement
   - trim `README.md` to project overview / quick-start / pointer content only
   - trim `docs/AGENT_RUNBOOK.md` to command-index guidance only
   - trim Horadus CLI skill surfaces to procedural helper / command reference only
   - route any detailed workflow-policy language back to `AGENTS.md`
   - update workflow policy helper generation and docs-freshness checks so the thin-surface contract is enforced

3. Validate
   - verify `README.md`, `docs/AGENT_RUNBOOK.md`, and Horadus CLI skill surfaces no longer contain representative canonical workflow-policy phrases that belong only in `AGENTS.md`
   - verify `AGENTS.md` still contains the canonical policy phrases
   - run direct workflow helper / docs-freshness checks
   - run targeted workflow tests if helper generation/drift checks change

4. Ship (PR, checks, merge, main sync)
   - close `TASK-308` in the ledgers on the PR head
   - run required local gates
   - push, open non-draft PR, address CI/review, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-12: Fold the narrower README-thinning idea into `TASK-308` instead of tracking it as a separate task.
- 2026-03-12: Keep `AGENTS.md` as the only workflow-policy owner; other workflow-facing docs/skills may summarize and point, but not restate canonical rules.

## Risks / Foot-guns

- Over-trimming quick-reference surfaces can make them useless -> keep minimal command/index value while removing only policy duplication
- Drift checks can be too narrow and miss restated policy -> use representative phrases and verify both owner and non-owner surfaces explicitly
- README cleanup can accidentally remove legitimate overview content -> preserve project summary and navigation pointers

## Validation Commands

- `uv run --no-sync python scripts/check_docs_freshness.py`
- `uv run --no-sync pytest tests/workflow -q -k "docs_freshness or repo_workflow"`
- `rg -n "safe-start TASK-|THUMBS_UP|review gate timeout|REVIEW_TIMEOUT_POLICY|Do not claim a task is complete" README.md docs/AGENT_RUNBOOK.md ops/skills/horadus-cli/`
- `rg -n "safe-start TASK-|THUMBS_UP|review gate timeout|REVIEW_TIMEOUT_POLICY|Do not claim a task is complete" AGENTS.md`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `AGENTS.md`
  - `README.md`
  - `docs/AGENT_RUNBOOK.md`
  - `ops/skills/horadus-cli/SKILL.md`
  - `ops/skills/horadus-cli/references/commands.md`
  - `tools/horadus/python/horadus_workflow/docs_freshness.py`
  - `tools/horadus/python/horadus_workflow/repo_workflow.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_policy.py`
  - `tests/workflow/`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
