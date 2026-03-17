# TASK-336: Separate Story Clusters from Stable Event-Claim Identity

## Status

- Owner: Codex
- Started: 2026-03-17
- Current state: In progress
- Planning Gates: Required — touches allowlisted Python hotspots and introduces new persistence semantics for replay/audit correctness

## Goal (1-3 lines)

Introduce a stable event-claim identity distinct from the mutable event cluster so
trend evidence, invalidation, and replay lineage survive cluster repairs and
contradictory subclaims without depending on one mutable event row alone.

## Inputs

- Spec/backlog references:
  - `tasks/CURRENT_SPRINT.md`
  - `tasks/BACKLOG.md` (`TASK-336`)
- Runtime/code touchpoints:
  - `src/storage/models.py`
  - `src/processing/event_clusterer.py`
  - `src/processing/tier2_classifier.py`
  - `src/processing/trend_impact_reconciliation.py`
  - `src/processing/pipeline_orchestrator.py`
  - `src/api/routes/events.py`
  - `alembic/`
  - `tests/`
- Preconditions/dependencies:
  - Keep existing event cluster id for raw-item linkage and event APIs
  - Preserve invalidation and evidence-reconciliation behavior for existing event-level callers

## Outputs

- Expected behavior/artifacts:
  - New stable `event_claims` persistence model under a mutable `event`
  - `trend_evidence` linked to `event_claim_id` as the primary stable identity while retaining `event_id`
  - Tier-2 and reconciliation flow that materializes one or more claim identities per event
  - Event API detail surface exposing claim-aware impacts
  - Migration, docs, and regression coverage
- Validation evidence:
  - Focused unit/integration tests for contradictory claims and claim-preserving evidence lineage
  - `make agent-check`

## Non-Goals

- Full event split/merge repair tooling across the product
- Broad rewrite of all event APIs around claim-first reads
- Historical backfill beyond a safe migration default for existing rows

## Scope

- In scope:
  - Add stable claim model and evidence foreign key
  - Create/refresh event claims during Tier-2 extraction
  - Reconcile evidence against claim identity instead of event id alone
  - Keep event invalidation and events API coherent with claim-aware evidence
  - Update schema docs and tests
- Out of scope:
  - New operator UI for claim management
  - Generalized multi-cluster claim migration workflows

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  - Add `event_claims` as the stable identity within an `event`, with one deterministic primary claim per distinct normalized claim text from Tier-2 output.
  - Keep `trend_evidence.event_id` for compatibility and cluster-level filtering, but require `trend_evidence.event_claim_id` for stable audit/replay semantics.
  - Use a deterministic fallback claim when Tier-2 emits no explicit claims so existing single-claim flows still work.
- Rejected simpler alternative:
  - Storing only claim ids inside `events.extracted_claims` JSON would not give durable foreign-keyed lineage for evidence, invalidation, or future split/merge repairs.
- First integration proof:
  - Contradictory claims in one event can coexist as separate `event_claims`, and active evidence rows point at the intended claim identity.
- Waivers:
  - This task keeps `src/storage/models.py` and `src/processing/pipeline_orchestrator.py` in allowlisted state rather than reducing those hotspots; follow-up extraction may still be needed.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement
3. Validate
4. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-03-17: Keep `events` as the mutable cluster container and add `event_claims` beneath it instead of replacing the event model outright. This preserves raw-item linkage and existing API semantics while giving evidence a stable identity.
- 2026-03-17: Retain `trend_evidence.event_id` alongside the new stable foreign key for compatibility and cheaper cluster-level queries during the transition.

## Risks / Foot-guns

- Missing claim rows for legacy or claim-less events -> create a deterministic fallback claim during migration/runtime reconciliation.
- Unique evidence semantics could regress if keyed only by event -> move active uniqueness to `(trend_id, event_claim_id, signal_type)`.
- Hotspot growth in allowlisted modules -> extract helper functions where needed and avoid broad refactors outside the claim/evidence path.

## Validation Commands

- `pytest tests/unit/processing/test_trend_impact_reconciliation.py`
- `pytest tests/unit/processing/test_tier2_classifier.py`
- `pytest tests/unit/api/test_events.py`
- `pytest tests/integration/test_feedback_invalidation.py`
- `pytest tests/integration/test_trend_evidence_reclassification.py`
- `make agent-check`

## Notes / Links

- Spec: backlog-only task; this exec plan is the authoritative planning artifact
- Relevant modules:
  - `src/storage/models.py`
  - `src/processing/trend_impact_reconciliation.py`
  - `src/processing/tier2_classifier.py`
  - `src/api/routes/events.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
