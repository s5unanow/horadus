# TASK-380: Add Implement-Mode Context-Pack Contract

## Status

- Owner: Codex
- Started: 2026-04-20
- Current state: Done
- Planning Gates: Required — shared workflow/context-pack contract and caller-visible CLI behavior

## Goal (1-3 lines)

Add `horadus tasks context-pack TASK-XXX --mode implement --format json` as
the first RFC-001 implement-mode retrieval surface while preserving the
current unflagged broad context-pack behavior.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` `TASK-380`,
  `tasks/specs/288-rfc-001-implementation-breakdown.md`,
  `docs/rfc/001-agent-context-retrieval.md`
- Runtime/code touchpoints: `tools/horadus/python/horadus_cli/`,
  `tools/horadus/python/horadus_workflow/`, `tests/horadus_cli/v2/`
- Preconditions/dependencies: `TASK-288` approved the Phase 1 implementation
  queue; no local index or external retrieval service is in scope.

## Outputs

- Expected behavior/artifacts: a mode-aware context-pack CLI contract with
  `default` and `implement` modes; implement-mode JSON metadata, task metadata,
  excluded-source notes, and compact code-backed policy payload; curated legacy
  policy registry for Phase 1.
- Validation evidence: targeted CLI/workflow tests, `make typecheck`, caller
  validation pack, `make agent-check`, integration proof, pre-push local review,
  and `uv run --no-sync horadus tasks local-gate --full`.

## Non-Goals

- Adding a local retrieval index or external retrieval service.
- Migrating all policy docs to retrieval front matter.
- Switching workflow callers to implement mode; that belongs to `TASK-383`.
- Adding task-spec retrieval metadata or canonical spec resolution; that
  belongs to `TASK-381`.
- Adding sprint extraction/test-candidate derivation; that belongs to
  `TASK-382`.

## Scope

- In scope: CLI `--mode` parsing, workflow payload branching, compact
  implement-mode JSON contract, docs for the new command, and regression tests.
- Out of scope: changing default text/JSON payload shape except for internal
  plumbing needed to route `default` mode.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: extend existing context-pack command
  handling and rendering helpers with an explicit mode enum and a separate
  implement-mode payload builder.
- Rejected simpler alternative: overloading `--format json` to silently emit a
  narrower payload would break compatibility for existing broad JSON callers.
- First integration proof: `uv run --no-sync horadus tasks context-pack TASK-380 --mode implement --format json` plus `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit` and `make test-integration-docker`.
- Hotspot Outcome: keep-flat-with-rationale — minimal CLI option registration may touch allowlisted `tools/horadus/python/horadus_cli/task_commands.py`; code-shape gates prevent ratchet growth.
- Waivers: none planned.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement mode-aware CLI and workflow payload
3. Add regression tests and docs
4. Validate with targeted packs, local review, and full local gate
5. Ship through `horadus tasks finish` and strict lifecycle verification

## Decisions (Timestamped)

- 2026-04-20: Keep default mode as the unflagged behavior to preserve current
  text and JSON contracts for existing callers.
- 2026-04-20: Keep implement mode JSON-only in this slice because the accepted
  RFC-001 Phase 1 surface is `--mode implement --format json`.

## Risks / Foot-guns

- Existing broad JSON callers could break if payload keys are removed -> add
  unchanged default JSON regression coverage.
- Implement mode could drift into `TASK-381`/`TASK-382` scope -> keep metadata
  explicit but compact, and record excluded sources for deferred behavior.
- Shared workflow helper changes can break other CLI entry points -> run the
  caller-aware validation pack and `make typecheck`.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_query.py tests/horadus_cli/v2/test_task_query_context_pack_modes.py tests/horadus_cli/v2/test_task_query_context_pack_support.py tests/workflow/test_task_workflow.py tests/workflow/test_repo_workflow.py -v -m unit` ✅
- `uv run --no-sync horadus tasks context-pack TASK-380 --mode implement --format json` ✅
- `make typecheck` ✅
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit` ✅
- `make agent-check` ✅
- `make test-integration-docker` ✅
- `uv run --no-sync horadus tasks local-review --format json` ✅
- `uv run --no-sync horadus tasks local-gate --full` ✅

## Notes / Links

- Spec: `tasks/specs/288-rfc-001-implementation-breakdown.md`
- RFC: `docs/rfc/001-agent-context-retrieval.md`
- Relevant modules:
  `tools/horadus/python/horadus_workflow/task_workflow_query.py`,
  `tools/horadus/python/horadus_workflow/task_workflow_context_pack_rendering.py`,
  `tools/horadus/python/horadus_cli/task_commands.py`
