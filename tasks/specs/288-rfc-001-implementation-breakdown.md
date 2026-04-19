# TASK-288: Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue [REQUIRES_HUMAN]

## Problem Statement

`docs/rfc/001-agent-context-retrieval.md` now captures the spike findings and a
phased retrieval design, but it does not yet exist as an approved execution
queue. Translating that RFC into concrete implementation tasks changes the
repo's workflow, task context surfaces, templates, and migration plan, so the
decomposition and sequencing need explicit human review.

This task should produce the implementation-task breakdown from the RFC and stop
for human approval before those follow-up tasks are finalized or started.

Human approval was provided in-thread on 2026-04-19 for amended Option A:
keep RFC-001 Phase 1 CLI-first, add `context-pack --mode implement`, adopt
task-spec front matter before policy-doc front matter, include compact
`CURRENT_SPRINT.md` extraction plus an orientation payload, expose
`autonomous_eligible` / human-gated state, reuse behavior-eval conventions for
`TASK-365`, and require caller audit plus planning/hotspot gates before
implementation tasks start.

## Inputs

- `docs/rfc/001-agent-context-retrieval.md`
- `docs/rfc/README.md`
- `tasks/CURRENT_SPRINT.md`
- `tasks/BACKLOG.md`
- `docs/AGENT_RUNBOOK.md`

## Outputs

- A proposed set of follow-up implementation tasks derived from RFC-001
- Human-reviewed sequencing and scope boundaries for those tasks
- Any agreed backlog/sprint updates captured only after explicit human approval

## Approved Implementation Queue

1. `TASK-380` Add Implement-Mode Context-Pack Contract
2. `TASK-381` Add Retrieval Metadata and Canonical Spec Resolution
3. `TASK-382` Add Task-Scoped Sprint Orientation and Test Candidates
4. `TASK-365` Add Retrieval Behavior Evals for RFC-001 Context Surfaces
5. `TASK-383` Switch Agent Workflow Surfaces to Implement Context-Pack Mode

## Human Decisions Captured

- Approve conservative Phase 1 / Option A before local indexing or hosted
  retrieval.
- Keep the existing Horadus CLI as the first implementation surface.
- Add task-spec front matter first; defer broad policy-doc front matter.
- Include both compact `CURRENT_SPRINT.md` task extraction and a small
  orientation payload.
- Make human-gated/autonomous eligibility explicit in implement-mode JSON.
- Reuse existing behavior-eval artifact and provenance conventions for
  retrieval evals.
- Require a caller audit and current planning/hotspot gates before switching
  autonomous workflows to the new implement-mode context pack.

## Non-Goals

- Implementing the RFC itself
- Autonomously approving the RFC-to-task breakdown
- Starting or finishing any RFC-derived implementation task

## Acceptance Criteria

- [x] RFC-001 is decomposed into concrete implementation-task candidates with clear scope boundaries
- [x] The proposed breakdown identifies any human decisions needed for sequencing or scope cuts
- [x] The task stops for human review/approval before finalizing the follow-up execution queue

## Validation

- `uv run --no-sync python scripts/check_docs_freshness.py`
