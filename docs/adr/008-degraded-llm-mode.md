# ADR-008: Degraded-Mode Policy for Sustained Tier-2 Failover

**Status**: Accepted  
**Date**: 2026-03-05  
**Deciders**: human-operator + Codex

## Context

Tier-2 extraction quality directly drives deterministic trend delta updates. The
runtime already supports retry + secondary failover, but sustained operation on
secondary routes (or silent quality regressions on the primary route) can change
probability semantics without a first-class policy.

This is a launch-risk: trend probability behavior must remain conservative and
auditable during provider incidents or quality drift.

## Decision

Introduce an explicit `degraded_llm` mode for Tier-2 that:

- Enters degraded mode on sustained Tier-2 failover over rolling windows
  (Redis time buckets + hysteresis).
- Also enters degraded mode when a Tier-2 gold-set canary gate fails for the
  configured primary Tier-2 model.
- In degraded mode:
  - Tier-2 extraction still runs, but the output is stored as provisional state
    rather than replacing canonical event/report fields,
  - but **trend deltas are not applied** (no `trend_evidence` writes),
  - and high-impact events are queued for replay once recovery is detected.
- If the primary Tier-2 model fails canary but an optional emergency Tier-2 model
  passes canary, run the pipeline with the emergency Tier-2 model and apply deltas
  normally for that run.

Replay is executed using a primary-only Tier-2 route (no failover) and applies
trend deltas once primary-quality behavior is restored.

## Consequences

### Positive

- Conservative semantics: avoids “half-truthy” auto-applied deltas during incidents.
- Replay works cleanly with existing idempotency (`trend_evidence` unique
  `(trend_id, event_id, signal_type)`) because degraded mode does not write evidence.
- Operators get explicit logs/metrics for degraded-mode entry/exit and replay behavior.

### Negative / Tradeoffs

- Trend probabilities may be stale during degraded windows until replay completes.
- Additional moving parts: Redis rolling-window accounting + DB replay queue + replay worker.
- Canary thresholds require tuning and periodic review as model behavior evolves.

## Implementation Notes

- Degraded-mode tracker: `src/processing/degraded_llm_tracker.py`
- Tier-2 canary gate: `src/processing/tier2_canary.py` using `ai/eval/gold_set.jsonl`
- Replay queue: `llm_replay_queue` table + replay worker task
- Pipeline holds deltas when degraded; provisional extraction records `_llm_policy`
  metadata and canonical promotion records the superseded provisional provenance.
