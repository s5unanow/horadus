# ADR-002: Claude API for LLM Processing

**Status**: Accepted  
**Date**: 2025-01-XX  
**Deciders**: Architecture review

## Context

We need LLM capabilities for:
- Relevance scoring (fast, cheap)
- Classification and entity extraction (accurate, structured)
- Summary generation
- Report narratives

We need reliable structured output and cost efficiency.

## Decision

Use **Anthropic Claude API** with a two-tier approach:
- **Tier 1 (Haiku)**: Fast relevance filtering
- **Tier 2 (Sonnet)**: Thorough classification

Use Pydantic models with Claude's tool use for structured outputs.

## Consequences

### Positive
- Claude excels at structured output via tool use
- 200K context window allows batch processing
- Haiku is cost-effective for filtering
- Sonnet balances quality and cost for classification
- Good at nuanced geopolitical analysis

### Negative
- Vendor lock-in to Anthropic
- API costs scale with volume
- Need internet connectivity

### Neutral
- Similar capabilities to GPT-4, so migration possible if needed

## Alternatives Considered

### Alternative 1: OpenAI GPT-4
- Pros: Well-established, good ecosystem
- Cons: Structured output less reliable, shorter context
- Why rejected: Claude's structured output is more consistent

### Alternative 2: Local models (Llama 3, Mistral)
- Pros: No API costs, full control, privacy
- Cons: Requires GPU infrastructure, lower quality
- Why rejected: Quality/effort tradeoff not worth it for MVP

### Alternative 3: Fine-tuned BERT for classification
- Pros: Fast, cheap, deterministic
- Cons: Requires labeled data, limited to trained categories
- Why rejected: Too rigid; will consider after collecting labeled data

## Cost Estimation

At 1,000 articles/day:
- Tier 1 (Haiku): ~$3/day (all articles)
- Tier 2 (Sonnet): ~$15/day (20% of articles)
- Total: ~$540/month

## References

- [Anthropic API Documentation](https://docs.anthropic.com/)
- [Claude Model Comparison](https://www.anthropic.com/claude)
