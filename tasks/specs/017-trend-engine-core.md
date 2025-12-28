# TASK-017: Trend Engine Core

## Overview

Implement the core probability engine that tracks trend likelihoods using
log-odds, applies evidence from news events, and manages time-based decay.

This is the **heart of the system**. The trend engine transforms classified
news signals into probability updates using deterministic, explainable math.

## Context

**Key Principle**: LLMs extract structured signals. This code computes deltas.

We use **log-odds** instead of raw probabilities because:
1. Additive: evidence naturally combines by addition
2. Bounded: converts back to valid 0-1 probability
3. Symmetric: equal evidence for/against produces equal magnitude changes
4. Standard: used in Bayesian inference and prediction markets

See `docs/adr/003-probability-model.md` for full rationale.

## Dependencies

- TASK-003: Database schema (trend tables must exist)
- None for core math (can be developed standalone)

## Requirements

### Core Functions

1. **Probability Conversion**
   - `prob_to_logodds(p: float) -> float`
   - `logodds_to_prob(lo: float) -> float`
   - Handle edge cases (p=0, p=1)

2. **Evidence Delta Calculation**
   - `calculate_evidence_delta(...)` - compute log-odds delta from event signals
   - Inputs: signal_type, base_weight, credibility, corroboration, novelty, direction
   - Output: delta value with bounds

3. **Trend Update**
   - `apply_evidence(trend, delta, event_id, reasoning)` - update trend's log-odds
   - Store evidence record for audit trail
   - Return updated probability

4. **Time Decay**
   - `apply_decay(trend, as_of_date)` - decay toward baseline
   - Uses configurable half-life per trend
   - Exponential decay formula

5. **Probability Queries**
   - `get_probability(trend) -> float` - current probability
   - `get_direction(trend, days=7) -> str` - rising/falling/stable
   - `get_change(trend, days) -> float` - delta over period

### Data Structures

```python
# From trend config (config/trends/*.yaml)
@dataclass
class TrendConfig:
    id: str
    name: str
    description: str
    baseline_probability: float  # Prior (e.g., 0.08 for 8%)
    decay_half_life_days: int    # How fast old news fades (e.g., 30)
    indicators: dict[str, IndicatorConfig]  # Signal types and weights

@dataclass
class IndicatorConfig:
    weight: float          # Base weight for this signal type (e.g., 0.04)
    keywords: list[str]    # Keywords that suggest this signal
    direction: str         # 'escalatory' or 'de_escalatory'


# Evidence from classified events
@dataclass
class EvidenceInput:
    event_id: UUID
    signal_type: str           # e.g., 'military_movement'
    source_credibility: float  # 0-1, from source config
    corroboration_count: int   # How many sources reported this
    novelty_score: float       # 1.0 if new, 0.3 if seen before
    direction: str             # 'escalatory' or 'de_escalatory'
    reasoning: str             # LLM explanation


# Computed output
@dataclass  
class EvidenceResult:
    delta_log_odds: float
    new_probability: float
    factors: dict[str, float]  # Breakdown of calculation
```

## Implementation

### Core Math Module

```python
# src/core/trend_engine.py

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.storage.models import Trend


# =============================================================================
# Constants
# =============================================================================

# Bounds to prevent extreme probabilities
MIN_PROBABILITY = 0.001  # 0.1%
MAX_PROBABILITY = 0.999  # 99.9%

# Maximum delta per single event (prevents any single event from dominating)
MAX_DELTA_PER_EVENT = 0.5  # About ±12% probability change at p=0.5


# =============================================================================
# Probability Conversion
# =============================================================================

def prob_to_logodds(p: float) -> float:
    """
    Convert probability to log-odds.

    Log-odds = ln(p / (1-p))

    Args:
        p: Probability between 0 and 1

    Returns:
        Log-odds value (can be any real number)

    Examples:
        >>> prob_to_logodds(0.5)
        0.0
        >>> prob_to_logodds(0.1)
        -2.197...
        >>> prob_to_logodds(0.9)
        2.197...
    """
    # Clamp to valid range
    p = max(MIN_PROBABILITY, min(MAX_PROBABILITY, p))
    return math.log(p / (1 - p))


def logodds_to_prob(lo: float) -> float:
    """
    Convert log-odds to probability.

    Probability = 1 / (1 + e^(-lo))

    Args:
        lo: Log-odds value

    Returns:
        Probability between MIN_PROBABILITY and MAX_PROBABILITY

    Examples:
        >>> logodds_to_prob(0.0)
        0.5
        >>> logodds_to_prob(-2.197)
        0.1...
        >>> logodds_to_prob(2.197)
        0.9...
    """
    try:
        p = 1 / (1 + math.exp(-lo))
    except OverflowError:
        # Very negative log-odds -> very small probability
        p = MIN_PROBABILITY if lo < 0 else MAX_PROBABILITY

    return max(MIN_PROBABILITY, min(MAX_PROBABILITY, p))


# =============================================================================
# Evidence Calculation
# =============================================================================

@dataclass
class EvidenceFactors:
    """Breakdown of factors used in delta calculation."""
    base_weight: float
    credibility: float
    corroboration: float
    novelty: float
    direction_multiplier: float
    raw_delta: float
    clamped_delta: float


def calculate_evidence_delta(
    signal_type: str,
    indicator_weight: float,
    source_credibility: float,
    corroboration_count: int,
    novelty_score: float,
    direction: str,  # 'escalatory' or 'de_escalatory'
) -> tuple[float, EvidenceFactors]:
    """
    Calculate log-odds delta from evidence factors.

    Formula:
        delta = base_weight * credibility * corroboration * novelty * direction

    Where:
        - base_weight: From trend indicator config (e.g., 0.04 for military_movement)
        - credibility: Source reliability (0-1)
        - corroboration: sqrt(num_sources) / 3, capped at 1.0
        - novelty: 1.0 for new info, 0.3 for repeated
        - direction: +1 for escalatory, -1 for de-escalatory

    Args:
        signal_type: Type of signal detected
        indicator_weight: Base weight from trend config
        source_credibility: Source reliability score (0-1)
        corroboration_count: Number of independent sources
        novelty_score: Novelty factor (0-1, typically 1.0 or 0.3)
        direction: 'escalatory' or 'de_escalatory'

    Returns:
        Tuple of (delta, factors breakdown)
    """
    # Corroboration factor: sqrt(n)/3, capped at 1.0
    # 1 source = 0.33, 4 sources = 0.67, 9+ sources = 1.0
    corroboration = min(1.0, math.sqrt(corroboration_count) / 3)

    # Direction multiplier
    direction_mult = 1.0 if direction == "escalatory" else -1.0

    # Calculate raw delta
    raw_delta = (
        indicator_weight
        * source_credibility
        * corroboration
        * novelty_score
        * direction_mult
    )

    # Clamp to prevent any single event from dominating
    clamped_delta = max(-MAX_DELTA_PER_EVENT, min(MAX_DELTA_PER_EVENT, raw_delta))

    factors = EvidenceFactors(
        base_weight=indicator_weight,
        credibility=source_credibility,
        corroboration=corroboration,
        novelty=novelty_score,
        direction_multiplier=direction_mult,
        raw_delta=raw_delta,
        clamped_delta=clamped_delta,
    )

    return clamped_delta, factors


# =============================================================================
# Trend Updates
# =============================================================================

class TrendEngine:
    """
    Engine for updating and querying trend probabilities.

    This class handles:
    - Applying evidence to update probabilities
    - Time-based decay toward baseline
    - Probability queries and comparisons

    Example:
        >>> engine = TrendEngine(db_session)
        >>> delta, factors = calculate_evidence_delta(...)
        >>> await engine.apply_evidence(trend, delta, event_id, "Military buildup reported")
        >>> prob = await engine.get_probability(trend)
    """

    def __init__(self, session):
        """
        Initialize trend engine.

        Args:
            session: Async database session
        """
        self.session = session

    async def apply_evidence(
        self,
        trend: Trend,
        delta: float,
        event_id: UUID,
        signal_type: str,
        factors: EvidenceFactors,
        reasoning: str,
    ) -> float:
        """
        Apply evidence delta to trend and record it.

        Args:
            trend: Trend to update
            delta: Log-odds delta to apply
            event_id: Source event ID
            signal_type: Type of signal
            factors: Breakdown of calculation factors
            reasoning: Human-readable explanation

        Returns:
            New probability after update
        """
        # Update trend
        trend.current_log_odds += delta
        trend.updated_at = datetime.utcnow()

        # Create evidence record
        from src.storage.models import TrendEvidence

        evidence = TrendEvidence(
            trend_id=trend.id,
            event_id=event_id,
            signal_type=signal_type,
            credibility_score=factors.credibility,
            corroboration_factor=factors.corroboration,
            novelty_score=factors.novelty,
            severity_score=factors.base_weight,
            delta_log_odds=delta,
            reasoning=reasoning,
        )

        self.session.add(evidence)
        await self.session.flush()

        return logodds_to_prob(trend.current_log_odds)

    async def apply_decay(
        self,
        trend: Trend,
        as_of: datetime | None = None,
    ) -> float:
        """
        Apply time-based decay toward baseline probability.

        Uses exponential decay with configurable half-life:
            new_lo = baseline_lo + (current_lo - baseline_lo) * decay_factor

        Where decay_factor = 0.5^(days_elapsed / half_life)

        Args:
            trend: Trend to decay
            as_of: Reference time (default: now)

        Returns:
            New probability after decay
        """
        as_of = as_of or datetime.utcnow()

        # Get baseline log-odds
        baseline_lo = prob_to_logodds(
            trend.definition.get("baseline_probability", 0.1)
        )

        # Get half-life
        half_life = trend.decay_half_life_days or 30

        # Calculate days since last update
        days_elapsed = (as_of - trend.updated_at).total_seconds() / 86400

        if days_elapsed <= 0:
            return logodds_to_prob(trend.current_log_odds)

        # Exponential decay factor
        decay_factor = math.pow(0.5, days_elapsed / half_life)

        # Apply decay toward baseline
        deviation = trend.current_log_odds - baseline_lo
        new_lo = baseline_lo + (deviation * decay_factor)

        trend.current_log_odds = new_lo
        trend.updated_at = as_of

        return logodds_to_prob(new_lo)

    def get_probability(self, trend: Trend) -> float:
        """Get current probability for trend."""
        return logodds_to_prob(trend.current_log_odds)

    async def get_probability_at(
        self,
        trend_id: UUID,
        at: datetime,
    ) -> float | None:
        """
        Get probability at a specific point in time.

        Uses trend_snapshots table.
        """
        from sqlalchemy import select
        from src.storage.models import TrendSnapshot

        result = await self.session.execute(
            select(TrendSnapshot.log_odds)
            .where(TrendSnapshot.trend_id == trend_id)
            .where(TrendSnapshot.timestamp <= at)
            .order_by(TrendSnapshot.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()

        if row is None:
            return None

        return logodds_to_prob(row)

    async def get_direction(
        self,
        trend: Trend,
        days: int = 7,
    ) -> str:
        """
        Get trend direction over specified period.

        Returns:
            'rising_fast': +5% or more
            'rising': +1% to +5%
            'stable': -1% to +1%
            'falling': -5% to -1%
            'falling_fast': -5% or more
        """
        current = self.get_probability(trend)
        past = await self.get_probability_at(
            trend.id,
            datetime.utcnow() - timedelta(days=days)
        )

        if past is None:
            return "stable"  # Not enough history

        delta = current - past

        if delta >= 0.05:
            return "rising_fast"
        elif delta >= 0.01:
            return "rising"
        elif delta <= -0.05:
            return "falling_fast"
        elif delta <= -0.01:
            return "falling"
        else:
            return "stable"

    async def get_change(
        self,
        trend: Trend,
        days: int,
    ) -> float | None:
        """
        Get absolute probability change over period.

        Returns:
            Probability delta (can be positive or negative),
            or None if not enough history.
        """
        current = self.get_probability(trend)
        past = await self.get_probability_at(
            trend.id,
            datetime.utcnow() - timedelta(days=days)
        )

        if past is None:
            return None

        return current - past
```

### Example Usage

```python
# In processing pipeline, after LLM classification:

from src.core.trend_engine import TrendEngine, calculate_evidence_delta

# Get engine
engine = TrendEngine(db_session)

# Get trend
trend = await get_trend_by_id(trend_id)

# Calculate delta from classified event
delta, factors = calculate_evidence_delta(
    signal_type="military_movement",
    indicator_weight=trend.indicators["military_movement"]["weight"],  # 0.04
    source_credibility=source.credibility_score,  # 0.95
    corroboration_count=event.source_count,  # 5
    novelty_score=1.0,  # New information
    direction="escalatory",
)

# Apply to trend
new_prob = await engine.apply_evidence(
    trend=trend,
    delta=delta,
    event_id=event.id,
    signal_type="military_movement",
    factors=factors,
    reasoning="Multiple sources report troop movements near border",
)

print(f"Trend '{trend.name}' probability: {new_prob:.1%}")
# Output: Trend 'EU-Russia Conflict' probability: 12.3%
```

## Testing

### Unit Tests

```python
# tests/unit/core/test_trend_engine.py

import math
import pytest
from datetime import datetime, timedelta

from src.core.trend_engine import (
    prob_to_logodds,
    logodds_to_prob,
    calculate_evidence_delta,
    MIN_PROBABILITY,
    MAX_PROBABILITY,
    MAX_DELTA_PER_EVENT,
)


class TestProbabilityConversion:
    """Tests for probability <-> log-odds conversion."""

    def test_prob_to_logodds_at_half(self):
        """p=0.5 should give log-odds of 0."""
        assert prob_to_logodds(0.5) == pytest.approx(0.0)

    def test_prob_to_logodds_symmetry(self):
        """p and 1-p should have opposite log-odds."""
        lo_low = prob_to_logodds(0.2)
        lo_high = prob_to_logodds(0.8)
        assert lo_low == pytest.approx(-lo_high)

    def test_logodds_to_prob_inverse(self):
        """Converting back and forth should preserve value."""
        for p in [0.1, 0.25, 0.5, 0.75, 0.9]:
            lo = prob_to_logodds(p)
            recovered = logodds_to_prob(lo)
            assert recovered == pytest.approx(p, rel=1e-6)

    def test_extreme_probabilities_clamped(self):
        """Extreme probabilities should be clamped."""
        assert logodds_to_prob(-1000) == MIN_PROBABILITY
        assert logodds_to_prob(1000) == MAX_PROBABILITY

    def test_zero_probability_clamped(self):
        """p=0 should be clamped to MIN_PROBABILITY."""
        lo = prob_to_logodds(0)
        assert logodds_to_prob(lo) >= MIN_PROBABILITY


class TestEvidenceCalculation:
    """Tests for evidence delta calculation."""

    def test_basic_escalatory_delta(self):
        """Basic escalatory evidence should produce positive delta."""
        delta, factors = calculate_evidence_delta(
            signal_type="military_movement",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=3,
            novelty_score=1.0,
            direction="escalatory",
        )
        assert delta > 0
        assert factors.direction_multiplier == 1.0

    def test_basic_deescalatory_delta(self):
        """De-escalatory evidence should produce negative delta."""
        delta, factors = calculate_evidence_delta(
            signal_type="diplomatic_talks",
            indicator_weight=0.03,
            source_credibility=0.9,
            corroboration_count=3,
            novelty_score=1.0,
            direction="de_escalatory",
        )
        assert delta < 0
        assert factors.direction_multiplier == -1.0

    def test_corroboration_scaling(self):
        """More sources should increase delta magnitude."""
        _, factors_1 = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
        )

        _, factors_9 = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=9,
            novelty_score=1.0,
            direction="escalatory",
        )

        assert factors_9.corroboration > factors_1.corroboration

    def test_low_credibility_reduces_delta(self):
        """Low credibility source should produce smaller delta."""
        delta_high, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.95,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
        )

        delta_low, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.30,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
        )

        assert abs(delta_high) > abs(delta_low)

    def test_novelty_affects_delta(self):
        """Repeated information should have less impact."""
        delta_new, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
        )

        delta_old, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=0.3,
            direction="escalatory",
        )

        assert abs(delta_new) > abs(delta_old)

    def test_delta_is_clamped(self):
        """Extreme inputs should not exceed MAX_DELTA_PER_EVENT."""
        delta, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=10.0,  # Unrealistically high
            source_credibility=1.0,
            corroboration_count=100,
            novelty_score=1.0,
            direction="escalatory",
        )

        assert abs(delta) <= MAX_DELTA_PER_EVENT


class TestDecay:
    """Tests for time-based probability decay."""

    # These would be async tests using the TrendEngine class
    # with mock database sessions
    pass
```

## Acceptance Criteria Checklist

- [ ] `prob_to_logodds` function with edge case handling
- [ ] `logodds_to_prob` function with clamping
- [ ] `calculate_evidence_delta` with all factors
- [ ] `TrendEngine.apply_evidence` with audit trail
- [ ] `TrendEngine.apply_decay` with configurable half-life
- [ ] `TrendEngine.get_probability` working
- [ ] `TrendEngine.get_direction` (rising/falling/stable)
- [ ] `TrendEngine.get_change` for arbitrary periods
- [ ] Comprehensive unit tests (>90% coverage)
- [ ] All edge cases tested (zero, extreme values)
- [ ] Type hints on all functions
- [ ] Docstrings with examples
- [ ] Integration with database models

## Notes

- This is the core business logic — get it right first
- Can be developed with unit tests before database is wired up
- Consider adding property-based tests with Hypothesis
- The decay formula may need tuning based on real-world usage
- Log all probability changes at INFO level for debugging
