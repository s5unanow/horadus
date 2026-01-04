# ADR-005: Two-Tier LLM Processing

**Status**: Accepted  
**Date**: 2026-01-03  
**Deciders**: Architecture review

## Context

LLM usage is required for:
- relevance scoring (high volume)
- extraction/classification (lower volume, higher quality requirements)

Constraints for this project:
- bounded and predictable cost (hard daily caps, kill switch)
- structured outputs (strict JSON) to avoid retry/repair loops
- resilience to ingestion spikes (breaking news, elections)

Using a single “best” model for all steps is simpler, but can be unnecessarily expensive for the high-volume filter stage.

## Decision

Use a two-tier LLM pipeline:

1. **Tier 1 (Filter / Relevance)**
   - cheap, fast model
   - inputs are short (title + excerpt + source metadata)
   - outputs are small: relevance score(s) and basic routing signals
   - items below threshold are marked `noise`

2. **Tier 2 (Classify / Extract / Summarize)**
   - higher quality model
   - runs only on items that pass Tier 1
   - outputs strict JSON: entities, claims, categories, per-trend signals, severity, confidence, and reasoning

Deterministic code (not the LLM) computes probability deltas from these structured signals.

## Consequences

### Positive
- materially lower cost under normal operation
- better throughput during ingestion spikes
- cleaner failure modes (Tier 1 can shed load; Tier 2 is rate-limited)
- easier evaluation: Tier 1 and Tier 2 can be benchmarked separately

### Negative
- pipeline complexity: two prompts/models, two failure surfaces
- potential false negatives: Tier 1 can drop items that Tier 2 would have used

### Mitigations
- keep Tier 1 threshold conservative and configurable
- allow a “single-model mode” for debugging or small-scale operation
- record sampling of Tier 1 “noise” for evaluation and drift checks

## Alternatives Considered

### Alternative 1: Single model for all steps
- Pros: simplest system
- Cons: higher cost and slower throughput; harder to bound spend during spikes
- Why rejected: bounded cost and throughput are core constraints for this project

### Alternative 2: Hand-built filter without LLM
- Pros: cheapest and deterministic
- Cons: high maintenance, brittle, language/domain drift, worse recall
- Why rejected: acceptable only as a later optimization if needed

## References

- `docs/adr/002-llm-provider.md`
- `docs/adr/003-probability-model.md`
