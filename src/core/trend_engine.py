"""
Trend Engine: Probability tracking using log-odds.

This module implements the core probability engine for tracking
geopolitical trends. It uses log-odds for mathematically sound
probability updates and time-based decay.

Key Principle: LLMs extract structured signals. This code computes deltas.

Example Usage:
    >>> from src.core.trend_engine import TrendEngine, calculate_evidence_delta
    >>> 
    >>> engine = TrendEngine(db_session)
    >>> delta, factors = calculate_evidence_delta(
    ...     signal_type="military_movement",
    ...     indicator_weight=0.04,
    ...     source_credibility=0.95,
    ...     corroboration_count=5,
    ...     novelty_score=1.0,
    ...     direction="escalatory",
    ... )
    >>> new_prob = await engine.apply_evidence(trend, delta, event_id, ...)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.storage.models import Trend, TrendEvidence

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Bounds to prevent extreme probabilities (0.1% to 99.9%)
MIN_PROBABILITY: float = 0.001
MAX_PROBABILITY: float = 0.999

# Maximum delta per single event (prevents any single event from dominating)
# At p=0.5, this translates to roughly ±12% probability change
MAX_DELTA_PER_EVENT: float = 0.5

# Default values
DEFAULT_DECAY_HALF_LIFE_DAYS: int = 30
DEFAULT_BASELINE_PROBABILITY: float = 0.10


# =============================================================================
# Probability Conversion Functions
# =============================================================================

def prob_to_logodds(p: float) -> float:
    """
    Convert probability to log-odds.
    
    Log-odds (or logit) = ln(p / (1-p))
    
    This transformation makes probability updates additive:
    - log_odds += delta is equivalent to Bayesian update
    - Naturally handles the 0-1 bounds
    
    Args:
        p: Probability between 0 and 1
        
    Returns:
        Log-odds value (can be any real number)
        
    Raises:
        ValueError: If p is not in valid range after clamping
        
    Examples:
        >>> prob_to_logodds(0.5)
        0.0
        >>> prob_to_logodds(0.1)  # doctest: +ELLIPSIS
        -2.197...
        >>> prob_to_logodds(0.9)  # doctest: +ELLIPSIS
        2.197...
        >>> prob_to_logodds(0.0)  # Clamped to MIN_PROBABILITY
        -6.906...
    """
    # Clamp to valid range to prevent math errors
    p_clamped = max(MIN_PROBABILITY, min(MAX_PROBABILITY, p))
    
    if p_clamped != p:
        logger.debug(
            "Probability clamped",
            original=p,
            clamped=p_clamped,
        )
    
    return math.log(p_clamped / (1 - p_clamped))


def logodds_to_prob(lo: float) -> float:
    """
    Convert log-odds to probability.
    
    Probability = 1 / (1 + e^(-lo))
    
    This is the inverse of prob_to_logodds and is also known
    as the logistic (sigmoid) function.
    
    Args:
        lo: Log-odds value (any real number)
        
    Returns:
        Probability between MIN_PROBABILITY and MAX_PROBABILITY
        
    Examples:
        >>> logodds_to_prob(0.0)
        0.5
        >>> logodds_to_prob(-2.197)  # doctest: +ELLIPSIS
        0.1...
        >>> logodds_to_prob(2.197)  # doctest: +ELLIPSIS
        0.9...
        >>> logodds_to_prob(-1000)  # Very negative -> MIN_PROBABILITY
        0.001
    """
    try:
        p = 1.0 / (1.0 + math.exp(-lo))
    except OverflowError:
        # Very negative log-odds -> near-zero probability
        # Very positive log-odds -> near-one probability
        p = MIN_PROBABILITY if lo < 0 else MAX_PROBABILITY
    
    # Clamp to valid range
    return max(MIN_PROBABILITY, min(MAX_PROBABILITY, p))


# =============================================================================
# Evidence Calculation
# =============================================================================

@dataclass
class EvidenceFactors:
    """
    Breakdown of factors used in delta calculation.
    
    Stored with each evidence record for transparency and debugging.
    
    Attributes:
        base_weight: Weight from trend indicator config
        credibility: Source reliability score
        corroboration: Factor from multiple sources
        novelty: Factor for new vs repeated info
        direction_multiplier: +1 for escalatory, -1 for de-escalatory
        raw_delta: Calculated delta before clamping
        clamped_delta: Final delta after clamping
    """
    base_weight: float
    credibility: float
    corroboration: float
    novelty: float
    direction_multiplier: float
    raw_delta: float
    clamped_delta: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "base_weight": self.base_weight,
            "credibility": self.credibility,
            "corroboration": self.corroboration,
            "novelty": self.novelty,
            "direction_multiplier": self.direction_multiplier,
            "raw_delta": self.raw_delta,
            "clamped_delta": self.clamped_delta,
        }


def calculate_evidence_delta(
    signal_type: str,
    indicator_weight: float,
    source_credibility: float,
    corroboration_count: int,
    novelty_score: float,
    direction: str,
) -> tuple[float, EvidenceFactors]:
    """
    Calculate log-odds delta from evidence factors.
    
    The formula is:
        delta = base_weight × credibility × corroboration × novelty × direction
    
    Where:
        - base_weight: From trend indicator config (e.g., 0.04 for military_movement)
        - credibility: Source reliability (0-1)
        - corroboration: sqrt(num_sources) / 3, capped at 1.0
        - novelty: 1.0 for new info, 0.3 for repeated
        - direction: +1 for escalatory, -1 for de-escalatory
    
    The result is clamped to MAX_DELTA_PER_EVENT to prevent any single
    event from having outsized influence.
    
    Args:
        signal_type: Type of signal detected (for logging)
        indicator_weight: Base weight from trend config
        source_credibility: Source reliability score (0.0 to 1.0)
        corroboration_count: Number of independent sources
        novelty_score: Novelty factor (0.0 to 1.0, typically 1.0 or 0.3)
        direction: 'escalatory' or 'de_escalatory'
        
    Returns:
        Tuple of (delta, factors_breakdown)
        
    Raises:
        ValueError: If direction is not valid
        
    Examples:
        >>> delta, factors = calculate_evidence_delta(
        ...     signal_type="military_movement",
        ...     indicator_weight=0.04,
        ...     source_credibility=0.9,
        ...     corroboration_count=3,
        ...     novelty_score=1.0,
        ...     direction="escalatory",
        ... )
        >>> delta > 0
        True
        >>> factors.direction_multiplier
        1.0
    """
    # Validate direction
    if direction not in ("escalatory", "de_escalatory"):
        raise ValueError(f"Invalid direction: {direction}")
    
    # Calculate corroboration factor
    # 1 source = 0.33, 4 sources = 0.67, 9+ sources = 1.0
    corroboration = min(1.0, math.sqrt(max(1, corroboration_count)) / 3.0)
    
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
    
    logger.debug(
        "Evidence delta calculated",
        signal_type=signal_type,
        delta=clamped_delta,
        was_clamped=raw_delta != clamped_delta,
        factors=factors.to_dict(),
    )
    
    return clamped_delta, factors


# =============================================================================
# Trend Engine
# =============================================================================

@dataclass
class TrendUpdate:
    """Result of applying evidence to a trend."""
    previous_probability: float
    new_probability: float
    delta_applied: float
    direction: str  # 'up', 'down', 'unchanged'


class TrendEngine:
    """
    Engine for updating and querying trend probabilities.
    
    This class handles:
    - Applying evidence to update probabilities
    - Time-based decay toward baseline
    - Probability queries and comparisons
    - Evidence audit trail
    
    All probability updates go through this class to ensure
    consistency and proper audit logging.
    
    Example:
        >>> engine = TrendEngine(db_session)
        >>> delta, factors = calculate_evidence_delta(...)
        >>> result = await engine.apply_evidence(
        ...     trend=trend,
        ...     delta=delta,
        ...     event_id=event_id,
        ...     signal_type="military_movement",
        ...     factors=factors,
        ...     reasoning="Multiple sources report troop movements",
        ... )
        >>> print(f"Probability: {result.new_probability:.1%}")
    """
    
    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize trend engine.
        
        Args:
            session: Async SQLAlchemy database session
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
    ) -> TrendUpdate:
        """
        Apply evidence delta to trend and record it.
        
        This is the main method for updating trend probabilities.
        It updates the trend's log-odds, creates an evidence record
        for audit purposes, and returns the update result.
        
        Args:
            trend: Trend to update
            delta: Log-odds delta to apply
            event_id: Source event ID
            signal_type: Type of signal detected
            factors: Breakdown of calculation factors
            reasoning: Human-readable explanation from LLM
            
        Returns:
            TrendUpdate with previous and new probabilities
        """
        from src.storage.models import TrendEvidence
        
        # Get previous probability
        previous_prob = logodds_to_prob(float(trend.current_log_odds))
        
        # Apply delta
        trend.current_log_odds = float(trend.current_log_odds) + delta
        trend.updated_at = datetime.utcnow()
        
        # Get new probability
        new_prob = logodds_to_prob(float(trend.current_log_odds))
        
        # Determine direction
        if delta > 0.001:
            direction = "up"
        elif delta < -0.001:
            direction = "down"
        else:
            direction = "unchanged"
        
        # Create evidence record
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
        
        logger.info(
            "Evidence applied to trend",
            trend_id=str(trend.id),
            trend_name=trend.name,
            event_id=str(event_id),
            signal_type=signal_type,
            delta=delta,
            previous_prob=previous_prob,
            new_prob=new_prob,
            direction=direction,
        )
        
        return TrendUpdate(
            previous_probability=previous_prob,
            new_probability=new_prob,
            delta_applied=delta,
            direction=direction,
        )
    
    async def apply_decay(
        self,
        trend: Trend,
        as_of: datetime | None = None,
    ) -> float:
        """
        Apply time-based decay toward baseline probability.
        
        Uses exponential decay with configurable half-life:
            new_lo = baseline_lo + (current_lo - baseline_lo) × decay_factor
        
        Where decay_factor = 0.5^(days_elapsed / half_life)
        
        This means after one half-life, the deviation from baseline
        is reduced by 50%. After two half-lives, 75%, etc.
        
        Args:
            trend: Trend to decay
            as_of: Reference time (default: now)
            
        Returns:
            New probability after decay
        """
        as_of = as_of or datetime.utcnow()
        
        # Get baseline
        baseline_prob = trend.definition.get(
            "baseline_probability",
            DEFAULT_BASELINE_PROBABILITY,
        )
        baseline_lo = prob_to_logodds(baseline_prob)
        
        # Get half-life
        half_life = trend.decay_half_life_days or DEFAULT_DECAY_HALF_LIFE_DAYS
        
        # Calculate days since last update
        days_elapsed = (as_of - trend.updated_at).total_seconds() / 86400.0
        
        if days_elapsed <= 0:
            return logodds_to_prob(float(trend.current_log_odds))
        
        # Exponential decay factor
        decay_factor = math.pow(0.5, days_elapsed / half_life)
        
        # Current log-odds
        current_lo = float(trend.current_log_odds)
        
        # Apply decay toward baseline
        deviation = current_lo - baseline_lo
        new_lo = baseline_lo + (deviation * decay_factor)
        
        # Update trend
        previous_lo = trend.current_log_odds
        trend.current_log_odds = new_lo
        trend.updated_at = as_of
        
        new_prob = logodds_to_prob(new_lo)
        
        logger.debug(
            "Decay applied to trend",
            trend_id=str(trend.id),
            trend_name=trend.name,
            days_elapsed=days_elapsed,
            decay_factor=decay_factor,
            previous_lo=previous_lo,
            new_lo=new_lo,
            new_prob=new_prob,
        )
        
        return new_prob
    
    def get_probability(self, trend: Trend) -> float:
        """
        Get current probability for trend.
        
        Args:
            trend: Trend to query
            
        Returns:
            Current probability (0 to 1)
        """
        return logodds_to_prob(float(trend.current_log_odds))
    
    async def get_probability_at(
        self,
        trend_id: UUID,
        at: datetime,
    ) -> float | None:
        """
        Get probability at a specific point in time.
        
        Uses trend_snapshots table to find the closest snapshot
        before the requested time.
        
        Args:
            trend_id: Trend ID
            at: Target datetime
            
        Returns:
            Probability at that time, or None if no snapshot exists
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
        
        return logodds_to_prob(float(row))
    
    async def get_direction(
        self,
        trend: Trend,
        days: int = 7,
    ) -> str:
        """
        Get trend direction over specified period.
        
        Compares current probability to probability N days ago.
        
        Args:
            trend: Trend to query
            days: Lookback period in days
            
        Returns:
            One of: 'rising_fast', 'rising', 'stable', 'falling', 'falling_fast'
        """
        current = self.get_probability(trend)
        past = await self.get_probability_at(
            trend.id,
            datetime.utcnow() - timedelta(days=days),
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
        
        Args:
            trend: Trend to query
            days: Lookback period in days
            
        Returns:
            Probability delta (positive or negative),
            or None if not enough history
        """
        current = self.get_probability(trend)
        past = await self.get_probability_at(
            trend.id,
            datetime.utcnow() - timedelta(days=days),
        )
        
        if past is None:
            return None
        
        return current - past
    
    async def get_top_evidence(
        self,
        trend_id: UUID,
        days: int = 7,
        limit: int = 10,
    ) -> list[TrendEvidence]:
        """
        Get top contributing evidence for a trend.
        
        Returns evidence records sorted by absolute delta magnitude.
        
        Args:
            trend_id: Trend ID
            days: Lookback period in days
            limit: Maximum number of records to return
            
        Returns:
            List of TrendEvidence records
        """
        from sqlalchemy import func, select
        from src.storage.models import TrendEvidence
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        result = await self.session.execute(
            select(TrendEvidence)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= cutoff)
            .order_by(func.abs(TrendEvidence.delta_log_odds).desc())
            .limit(limit)
        )
        
        return list(result.scalars().all())


# =============================================================================
# Utility Functions
# =============================================================================

def format_probability(p: float, precision: int = 1) -> str:
    """
    Format probability as a percentage string.
    
    Args:
        p: Probability (0 to 1)
        precision: Decimal places
        
    Returns:
        Formatted string like "12.3%"
    """
    return f"{p * 100:.{precision}f}%"


def format_direction(direction: str) -> str:
    """
    Format direction as human-readable string with emoji.
    
    Args:
        direction: Direction from get_direction()
        
    Returns:
        Formatted string like "↑ Rising Fast"
    """
    mapping = {
        "rising_fast": "⬆️ Rising Fast",
        "rising": "↗️ Rising",
        "stable": "➡️ Stable",
        "falling": "↘️ Falling",
        "falling_fast": "⬇️ Falling Fast",
    }
    return mapping.get(direction, direction)
