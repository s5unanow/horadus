# TASK-304: Realign Agent Workflow Docs and Remove Policy Duplication

## Status

- Owner: Codex
- Started: 2026-03-12
- Current state: In progress
- Planning Gates: Not Required — documentation cleanup with well-bounded repo surfaces

## Goal (1-3 lines)

Make the workflow documentation set internally consistent after the CLI/workflow
refactors. Keep `AGENTS.md` as the canonical workflow-policy owner, keep the
runbook as an operator command index, and keep the backlog focused on open task
definitions rather than duplicated workflow rules.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-304`)
  - documentation review findings recorded after `TASK-303`
- Runtime/code touchpoints:
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
  - `docs/RELEASING.md`
  - `tasks/BACKLOG.md`
  - `tasks/specs/`
  - open backlog entries that still reference pre-`TASK-303` workflow owners
  - `tools/horadus/python/horadus_workflow/`
  - `tests/workflow/`
- Preconditions/dependencies:
  - preserve the current `horadus tasks ...` / `horadus triage ...` command surface
  - preserve the current workflow ownership split introduced by `TASK-303`
  - do not rewrite task semantics while fixing documentation ownership

## Outputs

- Expected behavior/artifacts:
  - `AGENTS.md` remains the single canonical workflow-policy surface
  - `docs/AGENT_RUNBOOK.md` becomes a concise command/index document with minimal policy restatement
  - `docs/RELEASING.md` is aligned to the current canonical workflow CLI path and no longer teaches stale lower-level task-start commands where the agent flow should use `safe-start`
  - `tasks/BACKLOG.md` keeps only concise global task-ledger rules plus open task definitions
  - backlog-level start guidance is aligned to the current canonical CLI flow (`horadus tasks safe-start ...`) rather than old wrapper-first wording
  - the docs explicitly state that backlog entries stay concise while detailed implementation boundaries, migration strategy, risks, and validation belong in exec plans when one exists
  - stale backlog task/spec references to old workflow owners are updated to current workflow owners
  - docs clearly reflect the current workflow home under `tools/horadus/python/horadus_workflow`
  - docs-freshness / workflow-doc drift coverage includes the workflow-facing release guidance so stale CLI workflow instructions cannot drift silently outside the main agent-doc set
- Validation evidence:
  - targeted grep review showing duplicated policy blocks removed from runbook/backlog
  - docs freshness checks remain green
  - manual spot-check of key commands (`safe-start`, `context-pack`, `local-gate`, `finish`, `lifecycle`) against current CLI wording

## Non-Goals

- Explicitly excluded work:
  - changing runtime CLI behavior
  - changing task lifecycle policy semantics
  - broad product/backend docs rewrites outside workflow/operator surfaces
  - revisiting task estimates/priorities unless a stale reference forces a small backlog edit

## Scope

- In scope:
  - define documentation ownership boundaries explicitly:
    - `AGENTS.md` = canonical workflow policy
    - `docs/AGENT_RUNBOOK.md` = operator command index / usage notes
    - `tasks/BACKLOG.md` = concise task ledger and task definitions
    - other operator docs such as `docs/RELEASING.md` may summarize the workflow only insofar as they remain aligned to the canonical commands/policy owner
  - codify the planning-surface rule explicitly:
    - backlog entries stay concise and task-shaped
    - detailed implementation boundaries, migration strategy, risks, and validation belong in exec plans when one exists
  - realign the backlog's top-level task-start guidance to the current canonical CLI flow:
    - `uv run --no-sync horadus tasks safe-start TASK-XXX --name short-name`
    - wrapper commands are compatibility helpers only, not the canonical path
  - remove duplicated workflow-policy text from the runbook where it merely restates `AGENTS.md`
  - remove duplicated workflow-policy text from the backlog where it is not necessary for task-ledger operation, especially the current top-level task branching/completion policy block if it remains redundant
  - update stale command guidance to current canonical CLI usage
  - explicitly compress the runbook finish section back to command/index guidance and remove repeated completion/review-timeout/raw-`git`/`gh` policy text that belongs in `AGENTS.md`
  - realign workflow-facing release/operator docs to the same canonical CLI path where they currently preserve stale `horadus tasks start` guidance
  - update open task entries that still reference old workflow owners such as:
    - `src/core/docs_freshness.py`
    - `tests/unit/core/test_docs_freshness.py`
    - other pre-`TASK-303` workflow ownership paths if found
  - extend workflow-doc drift coverage so stale workflow command guidance in `docs/RELEASING.md` and similar operator docs is checked, not only `AGENTS.md` / runbook / backlog-adjacent surfaces
- Out of scope:
  - converting the runbook into a full architecture or policy document
  - changing historical archive task bodies
  - editing closed-task ledgers except where absolutely necessary for a link/path correction

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: one policy owner (`AGENTS.md`), one command index (`docs/AGENT_RUNBOOK.md`), one open-task ledger (`tasks/BACKLOG.md`)
- Rejected simpler alternative: leaving all three surfaces partially authoritative preserves drift and increases future review cost
- First integration proof: command guidance in the runbook and backlog points to the same current CLI flows described in `AGENTS.md`
- Waivers: concise cross-references back to `AGENTS.md` are allowed where the runbook or backlog needs to mention the policy owner explicitly

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory all overlapping workflow-policy sections across:
     - `AGENTS.md`
     - `docs/AGENT_RUNBOOK.md`
     - `tasks/BACKLOG.md`
   - inventory all stale workflow-owner references in open task entries, including:
     - `TASK-225`
     - `TASK-226`
     - `TASK-254`
     - `TASK-267`
   - inventory stale workflow-owner references in open specs, including:
     - `tasks/specs/275-finish-review-gate-timeout.md`
     - `tasks/specs/276-allow-silent-review-timeout-merge.md`
     - `tasks/specs/287-context-retrieval-spike.md`
   - inventory workflow-facing operator docs outside the current core set that can drift on CLI guidance, including:
     - `docs/RELEASING.md`
   - classify each duplicated section as:
     - must stay canonical in `AGENTS.md`
     - may stay as a short pointer/reference elsewhere
     - should be removed entirely
   - identify where the backlog-vs-exec-plan detail rule should be made explicit so it becomes canonical rather than implicit practice
   - identify the exact runbook duplication hotspot to compress during implementation:
     - the `horadus tasks finish` section and its repeated completion/review-timeout blocks
   - identify the exact backlog duplication hotspot to remove or compress during implementation:
     - the top-level `Task Branching Policy (Hard Rule)` block
   - identify the exact stale wrapper-first/start-flow wording to replace in the backlog:
     - `make task-preflight`
     - `make task-start TASK=XXX NAME=short-name`
   - identify stale lower-level task-start wording in operator docs outside the runbook, especially:
     - repeated `horadus tasks start TASK-XXX --name short-name` guidance in `docs/RELEASING.md`
   - identify current canonical CLI wording for:
     - `horadus tasks safe-start`
     - `horadus tasks context-pack`
     - `horadus tasks local-gate --full`
     - `horadus tasks finish`
     - `horadus tasks lifecycle --strict`

2. Implement
   - trim `docs/AGENT_RUNBOOK.md` so it keeps:
     - short command descriptions
     - operator usage notes
     - compatibility wrapper notes where helpful
     - links/pointers back to `AGENTS.md` for full workflow policy
   - remove or compress backlog-level workflow policy so `tasks/BACKLOG.md` keeps only:
     - minimal task-id / labeling / spec-contract rules
     - minimal branch/task metadata rules that are genuinely needed at the ledger level
     - open task definitions
   - update stale backlog task file lists to current workflow ownership paths
   - refresh verification/freshness metadata on edited docs where required, especially:
     - `docs/AGENT_RUNBOOK.md`
   - ensure any remaining repeated wording is intentional and short

3. Validate
   - run targeted searches to confirm duplicated policy blocks are gone
   - run targeted searches to confirm stale pre-`TASK-303` workflow-owner paths are gone from open backlog tasks
   - run targeted searches to confirm stale pre-`TASK-303` workflow-owner paths are gone from open task specs
   - run targeted searches to confirm workflow-facing release/operator docs no longer teach stale lower-level start guidance where `safe-start` is canonical
   - run docs freshness checks and any affected workflow tests if doc-path ownership references changed
   - manually verify the runbook still covers the canonical command set without contradicting `AGENTS.md`

4. Ship (PR, checks, merge, main sync)
   - include only the task-scoped documentation cleanup in the branch
   - rerun relevant local gates
   - open PR, address review, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-12: Keep `AGENTS.md` as the only canonical workflow-policy owner; other surfaces should reference or summarize it, not restate it wholesale
- 2026-03-12: Keep the backlog concise and move detailed cleanup logic into this exec plan instead of expanding the task entry

## Risks / Foot-guns

- Removing too much from the runbook can make it less useful -> keep command-oriented usage notes and wrapper hints
- Leaving too much in the runbook/backlog preserves drift risk -> prefer short pointers back to `AGENTS.md`
- Updating stale backlog task file lists can accidentally widen task scope -> keep edits limited to ownership/path alignment, not task redesign
- Leaving stale wrapper-first start guidance in the backlog keeps the docs internally contradictory -> make canonical CLI wording an explicit validation point
- Updating only backlog tasks but not task specs leaves the same ownership drift in another planning surface -> validate both `tasks/BACKLOG.md` and `tasks/specs/`
- Leaving `docs/RELEASING.md` outside workflow-doc drift coverage allows stale CLI workflow guidance to regress silently -> extend the checked workflow-doc surface
- Historical task/archive text can be edited accidentally -> do not touch archive bodies for this task

## Validation Commands

- `rg -n "safe-start|task-start|task-preflight|Primary-Task|review-gate timeout|THUMBS_UP|local-main-synced|close-ledgers" AGENTS.md docs/AGENT_RUNBOOK.md tasks/BACKLOG.md`
- `rg -n "src/core/docs_freshness.py|tests/unit/core/test_docs_freshness.py|src/core/repo_workflow.py|src/horadus_cli/v2/task_repo.py|src/horadus_cli/v2/task_workflow_core.py|src/horadus_cli/task_commands.py|src/horadus_cli/triage_commands.py" tasks/BACKLOG.md tasks/specs`
- `rg -n "horadus tasks start TASK-XXX --name short-name|horadus tasks safe-start TASK-XXX --name short-name" docs/RELEASING.md AGENTS.md docs/AGENT_RUNBOOK.md`
- `python3 scripts/check_docs_freshness.py`
- `uv run --no-sync pytest tests/workflow/test_docs_freshness.py -q`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `AGENTS.md`
  - `docs/AGENT_RUNBOOK.md`
  - `docs/RELEASING.md`
  - `tasks/BACKLOG.md`
  - `tasks/specs/275-finish-review-gate-timeout.md`
  - `tasks/specs/276-allow-silent-review-timeout-merge.md`
  - `tasks/specs/287-context-retrieval-spike.md`
  - `tools/horadus/python/horadus_workflow/`
  - `tests/workflow/`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
