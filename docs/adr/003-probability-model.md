# ADR-003: Log-Odds for Probability Tracking

**Status**: Accepted  
**Date**: 2025-01-XX  
**Deciders**: Architecture review

## Context

We need to track how news events affect the probability of geopolitical trends. Requirements:
- Probability must always be valid (0-1 range)
- Evidence should combine naturally
- Changes should be explainable and auditable
- Old evidence should decay over time

## Decision

Use **log-odds** representation internally:
- Store `log_odds = ln(p / (1-p))`
- Convert to probability only for display
- Evidence deltas are additive to log-odds
- Apply exponential decay based on time

### Formula

```python
import math

# Conversion
def prob_to_logodds(p: float) -> float:
    return math.log(p / (1 - p))

def logodds_to_prob(lo: float) -> float:
    return 1 / (1 + math.exp(-lo))

# Evidence delta
delta = (
    base_weight          # From trend.indicators (e.g., 0.04)
    * credibility        # Source reliability (0-1)
    * corroboration      # sqrt(sources) / 3, max 1
    * novelty            # 1.0 new, 0.3 repeat
    * direction          # +1 escalatory, -1 de-escalatory
)

# Apply evidence
trend.log_odds += delta

# Decay (daily)
decay_rate = 0.693 / half_life_days  # ln(2) / half_life
trend.log_odds = baseline + (trend.log_odds - baseline) * exp(-decay_rate)
```

## Consequences

### Positive
- **Mathematically sound**: Always produces valid probabilities
- **Additive**: Multiple pieces of evidence combine naturally
- **Symmetric**: Equal evidence for/against produces equal magnitude changes
- **Auditable**: Every delta is stored in `trend_evidence` table
- **Standard**: Used in prediction markets and Bayesian inference

### Negative
- Less intuitive than raw probabilities for non-technical users
- Requires conversion for display
- Base weights need empirical calibration

### Neutral
- Storage: same as storing probability (one float)

## Example

Starting probability: 8% (log-odds: -2.44)

Event: Russian military exercises near Baltic states
- Signal: military_movement (weight: 0.04)
- Source: Reuters (credibility: 0.95)
- 3 independent sources (corroboration: 0.58)
- New information (novelty: 1.0)
- Escalatory (direction: +1)

Delta: 0.04 × 0.95 × 0.58 × 1.0 × 1 = **0.022**

New log-odds: -2.44 + 0.022 = -2.42
New probability: **8.2%**

## Alternatives Considered

### Alternative 1: Raw Probability Updates
```python
prob += 0.01  # Simple addition
```
- Pros: Intuitive
- Cons: Can exceed 1.0, not additive in Bayesian sense
- Why rejected: Mathematically unsound

### Alternative 2: Bayesian with Explicit Likelihood Ratios
```python
posterior = prior * P(evidence|trend) / P(evidence)
```
- Pros: Most principled
- Cons: Requires modeling P(evidence|trend), complex
- Why rejected: Overkill for MVP; our approach is a simplification

### Alternative 3: Exponential Moving Average
```python
prob = alpha * new_signal + (1-alpha) * old_prob
```
- Pros: Simple, handles decay
- Cons: No principled evidence combination
- Why rejected: Log-odds is more principled for same complexity

## References

- [Log-odds in Bayesian inference](https://arbital.com/p/bayes_log_odds/)
- [Superforecasting](https://en.wikipedia.org/wiki/Superforecasting)
- [Prediction market scoring](https://www.metaculus.com/help/scoring/)
