# TASK-193: Degraded-mode policy for sustained LLM failover

## Status

- Owner: human-operator + Codex
- Started: 2026-03-03
- Current state: In progress (human-approved implementation)

## Goal (1-3 lines)

Define and implement a deterministic degraded-mode policy for sustained LLM
failover so auto-applied trend deltas remain conservative, explainable, and
auditable during model-quality degradation windows.

## Scope

- In scope:
  - Rolling failover ratio entry/exit criteria
  - Deterministic degraded-mode signal (`degraded_llm`) in pipeline state + metrics/logs
  - Conservative degraded behavior for trend delta application (attenuate or hold)
  - Optional bounded replay queue for high-impact items post-recovery
  - ADR + architecture/release docs updates for semantics change
  - Unit/integration coverage for policy behavior and transitions
- Out of scope:
  - New external queueing infrastructure
  - Broad model-routing redesign beyond degraded-mode policy

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Define policy constants + transition semantics (entry/exit hysteresis)
3. Add Tier-2 canary gate (gold set) + optional emergency Tier-2 model selection
4. Implement pipeline signaling + hold-deltas policy in degraded mode (no evidence writes)
5. Add bounded replay queue + replay worker (primary-only Tier-2) for post-recovery apply
6. Validate (unit/integration + docs consistency)
7. Human review/sign-off checkpoint (`[REQUIRES_HUMAN]`)
8. Ship (PR, checks, merge only after explicit sign-off, main sync)

## Decisions (Timestamped)

- 2026-03-03: Default policy target is conservative behavior in degraded mode;
  prefer minimizing false confidence over maximizing automation throughput.
- 2026-03-03: Human sign-off is mandatory before merge because this task changes
  probability semantics under degraded operating conditions.
- 2026-03-05: Chosen design is **A1**: shared rolling failover ratio via Redis
  time buckets + deterministic hold-deltas policy + bounded DB replay queue.
- 2026-03-05: Add a Tier-2 gold-set canary before bulk runs; if the primary Tier-2
  model fails canary but an optional emergency Tier-2 model passes, use emergency
  Tier-2 for the run and apply deltas normally; otherwise enter degraded mode and hold.

## Risks / Foot-guns

- Flapping between normal/degraded mode without hysteresis can cause unstable behavior.
- Overly aggressive attenuation/hold rules can starve trend updates and reduce operational usefulness.
- Replay queue growth must remain bounded to avoid recovery storms and cost spikes.
- Policy changes without clear provenance may reduce analyst trust in historical probabilities.
- Replay must not conflict with `trend_evidence` idempotency (`(trend_id, event_id, signal_type)` is unique);
  avoid writing evidence during degraded mode so replay can apply once on recovery.

## Validation Commands

- `make agent-check`
- `uv run --no-sync pytest tests/unit/ -v -m unit`
- `uv run --no-sync pytest tests/integration/ -v -m integration --allow-hosts=127.0.0.1,localhost`
- `make docs-freshness`

## Notes / Links

- Spec: `tasks/BACKLOG.md` (`TASK-193`)
- Assessment-Ref:
  - `artifacts/assessments/sa/daily/2026-03-02.md`
  - `PROPOSAL-2026-03-02-sa-failover-degraded-mode`
- Relevant modules:
  - `src/processing/`
  - `src/core/trend_engine.py`
  - `src/workers/`
  - `config/`
  - `docs/adr/`
  - `docs/ARCHITECTURE.md`
  - `docs/RELEASING.md`
