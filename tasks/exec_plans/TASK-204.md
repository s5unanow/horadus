# TASK-204: Recompute applied trend evidence when Tier-2 impacts change

## Status

- Owner: Codex
- Started: 2026-03-16
- Current state: Done
- Planning Gates: Required - task changes Tier-2/pipeline behavior, probability deltas, and allowlisted Python modules

## Goal (1-3 lines)

Ensure Tier-2 reclassification can safely reconcile already-applied trend evidence for an event.
When impact payloads change, the system must reverse stale deltas, apply the new deltas, and preserve lineage showing which evidence was superseded.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-204`)
- Runtime/code touchpoints: `src/processing/tier2_classifier.py`, `src/processing/pipeline_orchestrator.py`, `src/core/trend_engine.py`, `src/storage/models.py`
- Preconditions/dependencies: task must start through `horadus tasks safe-start`; trend evidence invalidation semantics and event merge behavior must remain auditable

## Outputs

- Expected behavior/artifacts: deterministic reconciliation of stale `TrendEvidence` when an event's Tier-2 impacts change; supersession lineage persisted on evidence rows; updated docs/tests
- Validation evidence: focused unit/integration tests, relevant local gates, and task workflow verification evidence

## Non-Goals

- Explicitly excluded work: redesigning Tier-2 prompts/schema, broad trend-engine scoring changes, unrelated event merge cleanup

## Scope

- In scope: impact diffing, evidence invalidation/replacement, trend state reconciliation, lineage fields/metadata updates, docs/tests
- Out of scope: manual operator adjudication UX, historical backfill/migration for already-stale rows unless runtime changes require a schema extension

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: reconcile evidence per event/trend/signal based on normalized impact payload diffs and use existing invalidation mechanics where possible
- Rejected simpler alternative: overwriting `event.extracted_claims["trend_impacts"]` without reversing applied deltas leaves `trends.current_log_odds` and evidence rows inconsistent
- First integration proof: rerun event classification on an event with prior evidence and observe old evidence superseded plus corrected trend log-odds
- Waivers: None

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-16: Start with runtime reconciliation on reclassification rather than a one-off repair script because the primary bug is ongoing stale evidence creation.

## Risks / Foot-guns

- Reversal logic could double-apply or miss deltas if evidence identity is not normalized -> use deterministic impact keys and targeted tests for changed severity/direction/trend membership
- Event merge flows may reuse or invalidate evidence differently from simple reclassification -> cover merge-related impact reapplication explicitly in tests
- Touched modules are already allowlisted for size -> prefer focused helpers/extractions instead of growing existing large methods

## Validation Commands

- `uv run --no-sync horadus tasks preflight`
- `uv run --no-sync horadus tasks safe-start TASK-204 --name recompute-trend-evidence`
- `pytest tests/unit/processing/test_pipeline_orchestrator.py tests/unit/processing/test_pipeline_orchestrator_additional.py tests/unit/core/test_trend_engine.py`
- `python scripts/check_code_shape.py`
- `uv run --no-sync horadus tasks lifecycle TASK-204 --strict`

## Notes / Links

- Spec: `tasks/BACKLOG.md`
- Relevant modules: `src/processing/pipeline_orchestrator.py`, `src/core/trend_engine.py`, `src/storage/models.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
