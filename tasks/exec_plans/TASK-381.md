# TASK-381: Add Retrieval Metadata and Canonical Spec Resolution

## Status

- Owner: Codex
- Started: 2026-04-20
- Current state: In progress
- Planning Gates: Required — shared task/spec retrieval contract and docs validation behavior

## Goal (1-3 lines)

Adopt the RFC-001 Phase 1 task-spec metadata slice and make context-pack
implement mode select a deterministic canonical task spec. Legacy specs should
continue to work, while ambiguous spec candidates fail closed for implement
callers.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` `TASK-381`,
  `tasks/specs/288-rfc-001-implementation-breakdown.md`,
  `docs/rfc/001-agent-context-retrieval.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_workflow/`,
  `tests/horadus_cli/v2/`, `tests/workflow/`, `tasks/specs/TEMPLATE.md`
- Preconditions/dependencies: `TASK-380` introduced implement-mode
  context-pack output; policy-doc front matter remains deferred.

## Outputs

- Expected behavior/artifacts: task-spec front matter guidance, structured
  backlog `**Spec**:` reference parsing, task-spec metadata parsing,
  supersession-aware canonical spec resolution, and implement-mode fail-closed
  ambiguity handling.
- Validation evidence: targeted CLI/workflow tests, `make typecheck`, workflow
  validation pack, `make agent-check`, integration proof, local review, and
  `uv run --no-sync horadus tasks local-gate --full`.

## Non-Goals

- Migrating all existing specs to retrieval-ready front matter.
- Requiring front matter for policy docs during Phase 1.
- Adding sprint-orientation or derived test-candidate payloads; those belong
  to `TASK-382`.
- Switching agent workflow callers to implement mode; that belongs to
  `TASK-383`.

## Scope

- In scope: task-spec-only metadata contract, deterministic spec resolution,
  implement-mode retrieval-source metadata, and regression tests.
- Out of scope: local retrieval index, hosted retrieval, policy-doc metadata
  enforcement, and broad task-ledger schema changes.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: add a task-spec resolver module used
  by existing task repo/query helpers, keeping default context-pack compatible
  and narrowing fail-closed behavior to implement mode.
- Rejected simpler alternative: choosing the first filename-glob match would be
  deterministic but would silently use the wrong spec when multiple candidates
  exist.
- First integration proof: `uv run --no-sync horadus tasks context-pack TASK-381 --mode implement --format json` plus targeted CLI/workflow tests.
- Hotspot Outcome: keep-flat-with-rationale — avoid material edits to existing
  allowlisted workflow hotspots by adding a focused resolver module and only
  touching the query/repo glue needed to call it.
- Waivers: none planned.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Add task-spec metadata and canonical resolution support
3. Add regression tests and docs/template updates
4. Validate with targeted packs, local review, and full local gate
5. Ship through `horadus tasks finish` and strict lifecycle verification

## Decisions (Timestamped)

- 2026-04-20: Keep metadata parsing limited to task specs so Phase 1 does not
  enforce policy-document front matter early.
- 2026-04-20: Treat explicit backlog `**Spec**:` references as the primary
  legacy selector before filename-glob fallback.
- 2026-04-20: Limit filename fallback to Markdown files matching
  `tasks/specs/{NNN}-*.md`; surface full resolver metadata so non-implement
  callers can detect ambiguity while preserving compatible `spec_paths`.

## Risks / Foot-guns

- Legacy tasks with multiple filename matches could get a wrong spec -> return
  an implement-mode validation error until metadata or `**Spec**:` resolves it.
- YAML parsing could become too broad -> parse only the small front matter
  subset needed for task specs.
- Shared workflow helper changes can break other CLI entry points -> run the
  caller-aware validation pack and `make typecheck`.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_repo.py tests/horadus_cli/v2/test_task_query_context_pack_modes.py tests/horadus_cli/v2/test_task_query.py tests/workflow/test_docs_freshness_planning_artifacts.py -v -m unit`
- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: `tasks/specs/288-rfc-001-implementation-breakdown.md`
- RFC: `docs/rfc/001-agent-context-retrieval.md`
- Relevant modules:
  `tools/horadus/python/horadus_workflow/task_repo.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_query.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_context_pack_implement.py`
