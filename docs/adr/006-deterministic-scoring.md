# ADR-006: Deterministic Trend Scoring from Structured LLM Signals

**Status**: Accepted  
**Date**: 2026-01-03  
**Deciders**: Architecture review

## Context

The system uses LLMs for extraction and classification, but direct probability
updates from free-form model output create three problems:
- non-repeatable behavior across runs/providers
- weak auditability for post-incident analysis
- difficult calibration and regression testing

This project requires explainable and bounded probability movement for
launch-readiness and operator trust.

## Decision

Use LLMs only to produce structured signals (signal type, direction, severity,
confidence, corroboration context, reasoning). Compute probability deltas in
deterministic code using log-odds math.

Implementation shape:
1. Tier-2 returns strict JSON classification output.
2. Deterministic trend engine computes `delta_log_odds` from weighted factors.
3. Every update persists factorized evidence in `trend_evidence`.

## Consequences

### Positive
- reproducible scoring behavior for the same structured inputs
- full audit trail for each trend movement
- easier calibration and ops debugging

### Negative
- extra engineering complexity vs direct LLM-to-probability updates
- scoring model updates require code/config changes and validation

### Neutral
- LLM quality still matters for extraction quality, but not for final math

## Alternatives Considered

### Alternative 1: Let LLM output probability deltas directly
- Pros: simpler initial implementation
- Cons: low explainability, unstable behavior, poor reproducibility
- Why rejected: violates auditability and deterministic-scoring requirements

### Alternative 2: Fully rule-based extraction with no LLM
- Pros: deterministic end-to-end
- Cons: brittle recall across domains/languages, heavy maintenance burden
- Why rejected: lower adaptability and slower iteration for this project scope

## References

- `docs/ARCHITECTURE.md`
- `src/core/trend_engine.py`
- `src/storage/models.py`
