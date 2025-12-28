# TASK-028: Risk Levels and Probability Bands

## Overview

Replace single probability numbers with a more nuanced presentation:
- **Risk Level**: Categorical (Low → Severe)
- **Probability Band**: Confidence interval (e.g., 5-15%)
- **Confidence Rating**: How certain we are in the estimate

This addresses the expert feedback: *"single probability number creates false precision and noisy swings."*

## Context

A user seeing "12.3% probability" may over-interpret small changes (12.3% → 12.8%).
Better: "Guarded risk (8-18%, medium confidence)" communicates uncertainty honestly.

## Requirements

### Risk Level Enum

```python
class RiskLevel(str, Enum):
    LOW = "low"           # < 10%
    GUARDED = "guarded"   # 10-25%
    ELEVATED = "elevated" # 25-50%
    HIGH = "high"         # 50-75%
    SEVERE = "severe"     # > 75%
```

### Probability Band Calculation

The band represents uncertainty based on:
1. **Evidence volume**: More evidence → narrower band
2. **Evidence recency**: Recent evidence → narrower band
3. **Source agreement**: Corroboration → narrower band

```python
def calculate_probability_band(
    probability: float,
    evidence_count_30d: int,
    avg_corroboration: float,
    days_since_last_evidence: int,
) -> tuple[float, float]:
    """
    Calculate confidence interval around probability.

    Returns (lower_bound, upper_bound).
    """
    # Base uncertainty (starts wide, narrows with evidence)
    base_uncertainty = 0.15  # ±15% default

    # Evidence volume factor (more evidence = less uncertainty)
    volume_factor = max(0.3, 1.0 - (evidence_count_30d / 50))

    # Recency factor (older evidence = more uncertainty)
    recency_factor = min(2.0, 1.0 + (days_since_last_evidence / 30))

    # Corroboration factor (more agreement = less uncertainty)
    corroboration_factor = max(0.5, 1.5 - avg_corroboration)

    # Combined uncertainty
    uncertainty = base_uncertainty * volume_factor * recency_factor * corroboration_factor

    # Calculate bounds (clamped to valid range)
    lower = max(0.001, probability - uncertainty)
    upper = min(0.999, probability + uncertainty)

    return (lower, upper)
```

### Confidence Rating

```python
class ConfidenceRating(str, Enum):
    LOW = "low"       # Wide band, few sources, old evidence
    MEDIUM = "medium" # Moderate band, some sources
    HIGH = "high"     # Narrow band, many corroborating sources

def get_confidence_rating(
    band_width: float,
    evidence_count: int,
    avg_corroboration: float,
) -> ConfidenceRating:
    """Determine confidence based on multiple factors."""
    score = 0

    # Narrow band = higher confidence
    if band_width < 0.10:
        score += 2
    elif band_width < 0.20:
        score += 1

    # More evidence = higher confidence
    if evidence_count >= 20:
        score += 2
    elif evidence_count >= 5:
        score += 1

    # Better corroboration = higher confidence
    if avg_corroboration >= 0.7:
        score += 1

    if score >= 4:
        return ConfidenceRating.HIGH
    elif score >= 2:
        return ConfidenceRating.MEDIUM
    else:
        return ConfidenceRating.LOW
```

## Implementation

### Update TrendResponse Schema

```python
# src/api/schemas/trends.py

class TrendResponse(BaseModel):
    id: UUID
    name: str
    description: str | None

    # Raw probability (keep for API consumers who want it)
    current_probability: float

    # NEW: Risk presentation
    risk_level: RiskLevel
    probability_band: tuple[float, float]
    confidence: ConfidenceRating

    # Existing
    direction: str
    change_7d: float | None
    is_active: bool
    updated_at: datetime

    # NEW: What moved it
    top_movers_7d: list[str]  # Brief descriptions of key events
```

### Update TrendEngine

```python
# src/core/trend_engine.py

def get_risk_level(probability: float) -> RiskLevel:
    """Map probability to categorical risk level."""
    if probability < 0.10:
        return RiskLevel.LOW
    elif probability < 0.25:
        return RiskLevel.GUARDED
    elif probability < 0.50:
        return RiskLevel.ELEVATED
    elif probability < 0.75:
        return RiskLevel.HIGH
    else:
        return RiskLevel.SEVERE


async def get_trend_presentation(
    self,
    trend: Trend,
) -> dict:
    """Get full trend presentation with risk level and bands."""
    probability = self.get_probability(trend)

    # Get evidence stats for band calculation
    stats = await self._get_evidence_stats(trend.id, days=30)

    # Calculate band
    band = calculate_probability_band(
        probability=probability,
        evidence_count_30d=stats["count"],
        avg_corroboration=stats["avg_corroboration"],
        days_since_last_evidence=stats["days_since_last"],
    )

    # Get confidence
    band_width = band[1] - band[0]
    confidence = get_confidence_rating(
        band_width=band_width,
        evidence_count=stats["count"],
        avg_corroboration=stats["avg_corroboration"],
    )

    # Get top movers
    top_events = await self.get_top_evidence(trend.id, days=7, limit=3)
    top_movers = [e.reasoning[:100] for e in top_events if e.reasoning]

    return {
        "probability": probability,
        "risk_level": get_risk_level(probability),
        "probability_band": band,
        "confidence": confidence,
        "top_movers_7d": top_movers,
    }
```

### API Response Example

```json
{
  "id": "uuid-here",
  "name": "EU-Russia Military Conflict",
  "current_probability": 0.123,
  "risk_level": "guarded",
  "probability_band": [0.08, 0.18],
  "confidence": "medium",
  "direction": "rising",
  "change_7d": 0.023,
  "top_movers_7d": [
    "Multiple sources report troop movements near border",
    "Diplomatic talks cancelled after incident"
  ]
}
```

## Testing

### Unit Tests

```python
class TestRiskLevels:
    def test_low_risk(self):
        assert get_risk_level(0.05) == RiskLevel.LOW
        assert get_risk_level(0.09) == RiskLevel.LOW

    def test_guarded_risk(self):
        assert get_risk_level(0.10) == RiskLevel.GUARDED
        assert get_risk_level(0.24) == RiskLevel.GUARDED

    def test_elevated_risk(self):
        assert get_risk_level(0.25) == RiskLevel.ELEVATED
        assert get_risk_level(0.49) == RiskLevel.ELEVATED

    def test_high_risk(self):
        assert get_risk_level(0.50) == RiskLevel.HIGH
        assert get_risk_level(0.74) == RiskLevel.HIGH

    def test_severe_risk(self):
        assert get_risk_level(0.75) == RiskLevel.SEVERE
        assert get_risk_level(0.99) == RiskLevel.SEVERE


class TestProbabilityBands:
    def test_more_evidence_narrows_band(self):
        band_few = calculate_probability_band(0.5, evidence_count_30d=2, ...)
        band_many = calculate_probability_band(0.5, evidence_count_30d=50, ...)

        width_few = band_few[1] - band_few[0]
        width_many = band_many[1] - band_many[0]

        assert width_many < width_few

    def test_band_clamped_to_valid_range(self):
        band = calculate_probability_band(0.05, ...)
        assert band[0] >= 0.001

        band = calculate_probability_band(0.95, ...)
        assert band[1] <= 0.999
```

## Acceptance Criteria

- [ ] `RiskLevel` enum with 5 levels
- [ ] `get_risk_level()` function with tests
- [ ] `calculate_probability_band()` function
- [ ] `ConfidenceRating` enum and `get_confidence_rating()` function
- [ ] `TrendResponse` schema updated with new fields
- [ ] API returns risk_level, probability_band, confidence
- [ ] Top movers included in response
- [ ] Unit tests for all new functions
- [ ] Documentation updated

## Notes

- Keep raw probability in API for backwards compatibility
- Band calculation parameters may need tuning with real data
- Consider storing bands in snapshots for historical analysis
