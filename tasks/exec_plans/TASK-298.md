# TASK-298: Add Phase -1 Planning Gates Without Heavy Process Overhead

## Status

- Owner: Codex
- Started: 2026-03-10
- Current state: Not started

## Goal (1-3 lines)

Strengthen Horadus planning quality before implementation starts by adding
short Phase -1 planning gates, surfacing them in workflow guidance/context
collection, and adding lightweight warn-only validation for a concretely
defined set of changed planning artifacts.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-251`, `TASK-298`)
- Runtime/code touchpoints:
  - `tasks/specs/TEMPLATE.md`
  - `tasks/exec_plans/TEMPLATE.md`
  - `docs/AGENT_RUNBOOK.md`
  - `src/horadus_cli/task_commands.py`
  - existing workflow/doc validation helpers under `src/core/` and `scripts/`
- Preconditions/dependencies:
  - preserve the repo’s lightweight planning posture for trivial work
  - avoid introducing a new planning subsystem when existing doc/workflow
    tooling can host the checks

## Outputs

- Expected behavior/artifacts:
  - updated task/spec template with:
    - core gates required for every applicable task
    - conditional gates that appear only when their trigger applies
    - explicit guidance for where the gates live when a task has no separate
      spec file yet
  - updated exec-plan template with Gate Outcomes / Waivers
  - runbook and context-pack guidance that surface the planning checklist
    before implementation for applicable tasks and stay quiet for
    non-applicable tasks
  - one repo-owned canonical good-example reference for new planning artifacts
  - warn-only validation for a concretely defined set of changed specs/plans
  - an explicit partition between `TASK-251` and `TASK-298`
  - explicit authoritative homes for:
    - gate content
    - waiver content
    - missing-artifact notices
  - one canonical applicability marker scheme and precedence rule
- Validation evidence:
  - unit/regression coverage for any CLI/context-pack or validation-tooling
    changes
  - a documented example path proving the template guidance is grounded in repo
    reality
  - one applicable-task proof and one non-applicable-task proof for the
    `context-pack` / validation quiet path

## Non-Goals

- Explicitly excluded work:
  - importing a full external spec-kit workflow
  - forcing heavy planning gates onto trivial doc-only or very small one-file
    tasks
  - rewriting old historical specs/plans just to satisfy the new template
  - changing task execution/merge policy outside what is needed to surface the
    new planning gates

## Scope

- In scope:
  - spec-template and exec-plan-template changes
  - applicability guidance for when the gates matter and where they must be
    recorded
  - context-pack/runbook surfacing of the planning checklist
  - warn-only validation for new/touched planning artifacts
  - documenting and partitioning the relationship to `TASK-251`
- Out of scope:
  - retrofitting every old spec/plan in the repo
  - building a multi-file planning artifact tree per task
  - hard-fail enforcement on day one

## Plan (Keep Updated)

1. Inventory the current planning entry points:
   - spec template
   - exec-plan template
   - runbook guidance
   - context-pack output path
   - existing doc/workflow validation hooks
2. Define the minimum Phase -1 planning-gate contract:
   - core gates for every applicable task:
     - simplicity
     - anti-abstraction
     - integration-first proof
   - conditional gates with explicit triggers:
     - determinism
     - LLM budget/safety
     - observability
3. Define one authoritative applicability rule using repo-visible signals:
   - one canonical marker scheme on the authoritative planning artifact
   - one precedence rule for:
     - explicit marker
     - `Exec Plan: Required`
     - quiet-path default
   - shared workflow/policy changes and explicit opt-in must resolve into that
     same marker scheme, not separate narrative rules
   - how backlog-authored tasks are covered before a dedicated spec exists
   - where the gates live for:
     - spec-backed tasks
     - exec-plan-backed tasks
     - backlog-only applicable tasks
     - quiet-path non-applicable tasks
4. Update `tasks/specs/TEMPLATE.md` with the new gate section and concise
   instructions on when a gate may be marked not applicable
5. Update `tasks/exec_plans/TEMPLATE.md` with Gate Outcomes / Waivers so plans
   record rejected simpler alternatives and justified complexity explicitly
   - define one authoritative waiver home by task shape:
     - exec-plan-backed applicable task -> exec plan
     - spec-backed applicable task without exec plan -> spec
     - backlog-only applicable task -> no inline waiver home; emit missing-artifact notice until spec/plan exists
6. Partition `TASK-251` and `TASK-298` explicitly in backlog/docs so ownership
   is reviewable:
   - `TASK-251` = baseline task/spec shape and the single canonical example
   - `TASK-298` = Phase -1 gates, applicability, validation, surfacing, and
     any gate-specific overlay on that same canonical example
7. Choose one repo-owned canonical example and point templates/runbook at it
8. Surface the planning checklist in agent-facing workflow guidance:
   - runbook
   - context-pack output state model:
     - applicable with authoritative artifact present
     - applicable backlog-only / missing artifact
     - applicable spec-backed without exec plan
     - non-applicable quiet path
   - name the minimum fields shown for each applicable state
   - explicit missing-artifact notice when a task is applicable but the
     authoritative planning artifact is absent
   - explicit quiet-path behavior for non-applicable tasks
9. Add warn-only validation for new/touched planning artifacts using existing
   tooling seams, not a new subsystem. Define “new or touched” operationally,
   for example as files changed relative to merge-base with `main`, with any
   local override path documented explicitly.
10. Make the validation bar more than headings-only:
   - applicable artifacts must include the required core gates
   - backlog entries must be checked too when they are the authoritative
     planning surface for an applicable task
   - omitted conditional gates must be marked not applicable with a short
     reason
   - repo-owned trigger rules must exist for each conditional gate so the
     validator can tell omission from compliance
   - the Integration-First Gate must name one concrete proof target and the
     contract/dependency/invariant it is expected to exercise
11. Add tests for the changed workflow/doc tooling and confirm:
   - one applicable-task path surfaces the planning block correctly
   - one applicable-but-missing-artifact path emits the expected notice
   - one non-applicable fixture or temp-task path stays quiet
   - warn-only validation scopes only the intended changed artifacts,
     including an applicable backlog-entry path when no separate spec exists
12. Validate locally and stop at a clean planning/process patch, not a broader
   workflow redesign

## Decisions (Timestamped)

- 2026-03-10: Treat this as a focused follow-up to `TASK-251` rather than a
  replacement; `TASK-251` remains the broader normalization umbrella, while
  this task adds the missing Phase -1 gates and warn-only validation.
- 2026-03-10: Keep the gates short and decision-shaped so the repo gains
  stronger planning discipline without importing heavyweight process.
- 2026-03-10: Start validation in warn-only mode and limit scope to new or
  touched artifacts to avoid historical debt blocking active work.
- 2026-03-10: Split gates into core vs conditional sets so the repo gets
  stronger planning without forcing routine `N/A` boilerplate.
- 2026-03-10: The applicability rule must use repo-visible signals, not
  subjective author intent, so `context-pack` and warn-only validation can
  behave deterministically.
- 2026-03-10: Shared-workflow applicability and explicit planning-gate opt-in
  must be expressed through repo-owned markers or artifact rules, otherwise the
  validator cannot enforce them consistently.
- 2026-03-10: Backlog-only applicable tasks may carry the applicability marker,
  but detailed gates and waivers should not be split across backlog and plan
  surfaces; until the authoritative artifact exists, the workflow should emit a
  consistent missing-artifact notice.

## Risks / Foot-guns

- Planning gates become process theater -> keep prompts short, concrete, and
  tied to repo-native examples
- Validation becomes noisy and ignored -> warn only at first, and scope it to
  changed artifacts
- Templates become too generic -> anchor them with one good repo-owned example
- Context-pack becomes bloated -> surface only the short checklist and
  applicability guidance, not a large methodology dump
- `TASK-251` and `TASK-298` drift into overlapping ambiguity -> partition the
  two tasks explicitly in backlog/docs and keep acceptance criteria non-overlapping
- Backlog-defined tasks bypass the new gates -> define where gates live before
  a dedicated spec exists and make the missing artifact visible in workflow guidance
- Warn-only validation becomes either too noisy or too weak -> define “changed
  artifacts” operationally and validate one positive and one quiet-path example
- Waiver handling becomes inconsistent across planning surfaces -> define one
  authoritative waiver home for each applicable task shape
- Marker precedence becomes ambiguous -> define a single marker scheme and one
  precedence order rather than mixed heuristics

## Validation Commands

- `uv run --no-sync pytest tests/unit/test_cli.py -q`
- `uv run --no-sync pytest tests/unit/core/ -q`
- `uv run --no-sync horadus tasks context-pack TASK-298`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Parent task:
  - `TASK-251`
- Relevant files:
  - `tasks/BACKLOG.md`
  - `tasks/specs/TEMPLATE.md`
  - `tasks/exec_plans/TEMPLATE.md`
  - `docs/AGENT_RUNBOOK.md`
  - `src/horadus_cli/task_commands.py`
