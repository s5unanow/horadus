# TASK-287: Spike Markdown-First Context Retrieval for Agent Workflow

## Problem Statement

Horadus currently provides task context through a mix of backlog entries, sprint
status, project-level narrative, runbook guidance, and direct file inspection.
That works, but it also pulls bookkeeping and historical material into the same
working set as the implementation-critical spec, code, and tests. The result is
more noise than necessary, slower orientation, and higher risk of stale context
shaping decisions.

This spike should determine how far the repo can go with Markdown-first
retrieval, lightweight metadata, and narrower context-pack output before adding
heavier infrastructure.

## Inputs

- Existing context surfaces in `tasks/BACKLOG.md`, `tasks/CURRENT_SPRINT.md`,
  `PROJECT_STATUS.md`, `AGENTS.md`, and `docs/AGENT_RUNBOOK.md`
- Current `horadus tasks context-pack` behavior in `src/horadus_cli/v2/task_commands.py`
- Current task/spec templates in `tasks/specs/TEMPLATE.md`
- External guidance for retrieval, prompt variables, and optional MCP/resource
  patterns

## Outputs

- A repo document capturing the spike findings, options, tradeoffs, and
  recommended direction for agent-context retrieval
- A proposed document metadata schema for Markdown-first retrieval
- A proposed section chunking/indexing model and retrieval mode design
- A recommended near-term implementation slice for Horadus

## Non-Goals

- Implementing the retrieval system itself
- Replacing Markdown authoring with a new source format
- Deciding the final production architecture for all future agent tooling

## Acceptance Criteria

- [ ] The spike documents the current context-noise problem and distinguishes high-signal inputs from bookkeeping noise
- [ ] The spike evaluates whether existing Markdown docs are sufficient for precise retrieval and identifies any minimal metadata or structure additions needed
- [ ] The spike compares multiple implementation options with explicit tradeoffs
- [ ] The spike recommends a preferred near-term path for Horadus, including schema, chunking/indexing rules, retrieval modes, and guardrails
- [ ] The spike output is captured in a repo document suitable for future review and implementation planning

## Validation

- `uv run --no-sync python scripts/check_docs_freshness.py`
