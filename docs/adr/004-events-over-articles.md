# ADR-004: Events as the Unit of Analysis (Not Articles)

**Status**: Accepted  
**Date**: 2026-01-04  
**Deciders**: Architecture review

## Context

Raw news items (articles/posts/messages) are noisy:
- duplicates and syndication are common (wire copy, reposts)
- multiple outlets cover the same underlying development
- a single item rarely contains enough context to drive probability updates safely

For trend tracking, we want probability changes to be:
- explainable (“what happened?”)
- robust to duplicates
- auditable (evidence tied to an underlying real-world development)

## Decision

Treat **Event** as the primary unit of analysis and storage for “what happened”.

- Ingestion produces `RawItem` records.
- Processing deduplicates and clusters `RawItem` into `Event`.
- Trend evidence (`TrendEvidence`) references the **Event**, not individual items.
- Reports summarize trends using events and evidence, not raw articles.

## Consequences

### Positive
- reduces duplicate counting and over-updating during news spikes
- creates a stable object to attach structured extraction (who/what/where/when/claims)
- enables contradiction tracking and lifecycle management at the event level
- improves reporting quality (reports talk about events, not a list of articles)

### Negative
- requires clustering logic and embeddings earlier in the pipeline
- harder to debug than “article-level” systems without good tooling/observability

### Mitigations
- store provenance links (`event_items`) so you can always trace back to sources
- store `primary_item_id` as the “best” representative source
- keep clustering thresholds configurable and add evaluation fixtures over time

## Alternatives Considered

### Alternative 1: Articles as the unit of analysis
- Pros: simpler to implement, easy traceability
- Cons: duplicates/syndication inflate evidence; probability deltas become noisy
- Why rejected: violates explainability and robustness requirements

## References

- `docs/ARCHITECTURE.md` (processing and clustering flow)
- `docs/DATA_MODEL.md` (events, raw_items, event_items)
