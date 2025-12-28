# ADR-002: LLM Provider Selection (Revised)

**Status**: Accepted
**Date**: 2025-12-28
**Deciders**: Architecture review
**Previous Decision**: Claude API (Haiku/Sonnet)

## Context

We need LLM capabilities for:
- Relevance scoring (fast, cheap)
- Classification and entity extraction (accurate, structured)
- Summary generation
- Report narratives

We need reliable structured output (JSON) and extreme cost efficiency for a personal project.

## Decision

Use **OpenAI models** with a “simple default” and an “optional optimization path”.

### Operational Default (Start Here)
- **Tier 1 (Filter)**: `gpt-4o-mini`
- **Tier 2 (Classify/Summarize)**: `gpt-4o-mini`

**Why**: One model minimizes complexity while keeping strong JSON/schema adherence and predictable quality.

### Optional Optimization Path (When Cost/Volume Requires It)
- **Tier 1 (Filter)**: a cheaper “classification-oriented” model *if available in your account and priced lower* (expert review suggested `gpt-4.1-nano`)
- **Tier 2 (Classify/Summarize)**: `gpt-4o-mini`

**Why**: Tier 1 is high-volume and can tolerate simpler reasoning; Tier 2 is lower-volume and quality-sensitive.

## Consequences

### Positive
- **Cost control**: Model choice plus hard daily caps keep spend bounded for a personal project.
- **Reliable structured output**: Prioritize strict JSON/schema adherence to reduce “retry costs”.
- **Simplified stack**: Default is single model; optimization is optional.
- **Performance**: Capable reasoning for classification
- **Ecosystem**: Easy integration with generic OpenAI client libraries

### Negative
- **Pricing/availability changes**: Model names and prices move; keep this ADR updated with “as-of” dates.
- **Latency tradeoffs**: If using any batch/offline processing, you may lose near-real-time behavior.
- **Narrative nuance**: Some models/providers may write better prose; keep narratives optional and constrained.

## Alternatives Considered

### Alternative 1: Anthropic Claude (Haiku + Sonnet)
- **Pros**: Excellent writing style, massive context.
- **Cons**: Expensive.
    - Haiku: $0.25/M in, $1.25/M out
    - Sonnet: $3.00/M in, $15.00/M out
- **Estimated Cost**: Higher than `gpt-4o-mini` under similar assumptions; exact number depends on current model generation and output tokens.
- **Why Rejected**: Too expensive for personal hobby project.

### Alternative 2: Google Gemini Flash (current generation)
- **Pros**: Often among the cheapest, large context.
- **Cons**: Strict schema adherence can be less consistent, increasing retries/repair work.
- **Why Rejected (for default)**: Prefer fewer retries and simpler ops; keep as fallback/experiment.

### Alternative 3: Local Llama 3 (8B)
- **Pros**: Potentially very low per-token cost if you already have hardware.
- **Cons**: Operational overhead; quality/JSON adherence often lower; hidden costs (hosting, time).
- **Why Rejected**: Operational overhead.

## Cost Estimation (How to Think About It)

Cost is dominated by three factors:
1) **Items/day** (source volume)  
2) **Input tokens per item** (how much text you send)  
3) **Tier-2 pass rate** (how many items survive Tier 1)

### Example Assumptions (Replace With Measured Values)
- 1,000 items/day
- ~1,500 input tokens/item for Tier 1
- 20% pass rate to Tier 2
- Tier 2 uses ~1,500 input + ~500 output tokens/item

### Example Prices (Must Be Verified “As Of”)
This ADR previously used:
- `gpt-4o-mini`: $0.15 / 1M input tokens, $0.60 / 1M output tokens

Pricing changes; verify on vendor pricing pages and update this ADR with an “as-of” date.

### Why the “Optional Optimization Path” Helps
If Tier 1 moves to a cheaper classifier model (expert review suggested `gpt-4.1-nano`) and Tier 2 stays on `gpt-4o-mini`, the monthly cost can drop materially **if**:
- Tier 1 volume is high
- Tier 2 pass rate is low
- The cheaper model doesn’t increase retries/repair costs

## Cost-Reduction Levers (Higher Impact Than Model Shopping)
1. **Trim inputs hard**: send `title + lead + extracted key sentences`, not full articles.
2. **Deduplicate early**: hash/URL canonicalization before Tier 1; cluster before Tier 2 where possible.
3. **Lower source volume**: fewer feeds, slower polling, “quiet hours”.
4. **Batch/offline processing (optional)**: some providers offer cheaper asynchronous processing; accept latency.
5. **Prompt caching (optional)**: can reduce repeated instruction costs where supported.
6. **Hard daily caps**: implement a kill-switch so a bug can’t burn your budget.

## References (Update With Current Links/Prices)
- OpenAI pricing: https://openai.com/pricing
- Anthropic pricing: https://www.anthropic.com/pricing
- Google Gemini pricing: https://ai.google.dev/pricing

## Notes
- A previous draft referenced “~$540/month”; treat that as a discarded estimate. Costs are extremely sensitive to token assumptions and output length.
- For a personal system with ~20 trends, correctness/traceability and bounded spend matter more than squeezing every cent out of the model choice.
