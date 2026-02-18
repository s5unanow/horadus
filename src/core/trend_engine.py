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

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from inspect import isawaitable
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

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
DEFAULT_NOVELTY_MIN_SCORE: float = 0.30
DEFAULT_NOVELTY_RECOVERY_HALF_LIFE_DAYS: float = 7.0


# =============================================================================
# Time Helpers
# =============================================================================


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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
        severity: Magnitude of the signal (0.0-1.0)
        confidence: LLM classification confidence (0.0-1.0)
        credibility: Source reliability score
        corroboration: Factor from multiple sources
        novelty: Factor for new vs repeated info
        evidence_age_days: Age of the signal/event in days
        temporal_decay_multiplier: Time-decay multiplier applied to this indicator
        direction_multiplier: +1 for escalatory, -1 for de-escalatory
        raw_delta: Calculated delta before clamping
        clamped_delta: Final delta after clamping
    """

    base_weight: float
    severity: float
    confidence: float
    credibility: float
    corroboration: float
    novelty: float
    evidence_age_days: float
    temporal_decay_multiplier: float
    direction_multiplier: float
    raw_delta: float
    clamped_delta: float

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary for JSON storage."""
        return {
            "base_weight": self.base_weight,
            "severity": self.severity,
            "confidence": self.confidence,
            "credibility": self.credibility,
            "corroboration": self.corroboration,
            "novelty": self.novelty,
            "evidence_age_days": self.evidence_age_days,
            "temporal_decay_multiplier": self.temporal_decay_multiplier,
            "direction_multiplier": self.direction_multiplier,
            "raw_delta": self.raw_delta,
            "clamped_delta": self.clamped_delta,
        }


def calculate_recency_novelty(
    *,
    last_seen_at: datetime | None,
    as_of: datetime | None = None,
    min_score: float = DEFAULT_NOVELTY_MIN_SCORE,
    recovery_half_life_days: float = DEFAULT_NOVELTY_RECOVERY_HALF_LIFE_DAYS,
) -> float:
    """
    Calculate a continuous novelty score from prior evidence recency.

    - No prior evidence => 1.0 (fully novel)
    - Very recent prior evidence => near `min_score`
    - Older prior evidence => asymptotically approaches 1.0
    """
    if last_seen_at is None:
        return 1.0

    min_score = max(0.0, min(1.0, min_score))
    half_life = max(0.1, recovery_half_life_days)
    now = _as_utc(as_of) if as_of is not None else datetime.now(UTC)
    age_days = max(0.0, (now - _as_utc(last_seen_at)).total_seconds() / 86400.0)

    novelty = 1.0 - (1.0 - min_score) * math.exp(-age_days / half_life)
    return max(min_score, min(1.0, novelty))


def calculate_evidence_delta(
    signal_type: str,
    indicator_weight: float,
    source_credibility: float,
    corroboration_count: float,
    novelty_score: float,
    direction: str,
    severity: float = 1.0,
    confidence: float = 1.0,
    evidence_age_days: float = 0.0,
    indicator_decay_half_life_days: float | None = None,
) -> tuple[float, EvidenceFactors]:
    """
    Calculate log-odds delta from evidence factors.

    The formula is:
        delta = base_weight * severity * confidence * credibility * corroboration * novelty * direction

    Where:
        - base_weight: From trend indicator config (e.g., 0.04 for military_movement)
        - severity: Magnitude of the signal (0.0-1.0), e.g., routine=0.2, major=0.8
        - confidence: LLM's certainty in classification (0.0-1.0)
        - credibility: Source reliability (0-1)
        - corroboration: sqrt(effective_independent_sources) / 3, capped at 1.0
        - novelty: 1.0 for new info, 0.3 for repeated
        - direction: +1 for escalatory, -1 for de-escalatory

    The result is clamped to MAX_DELTA_PER_EVENT to prevent any single
    event from having outsized influence.

    Args:
        signal_type: Type of signal detected (for logging)
        indicator_weight: Base weight from trend config
        source_credibility: Source reliability score (0.0 to 1.0)
        corroboration_count: Effective independent corroboration score (supports fractional penalties)
        novelty_score: Novelty factor (0.0 to 1.0, typically 1.0 or 0.3)
        direction: 'escalatory' or 'de_escalatory'
        severity: Magnitude of the signal (0.0 to 1.0, default 1.0)
                  - 0.1-0.3: Routine (exercises, standard diplomatic statements)
                  - 0.4-0.6: Significant (unusual activity, strong rhetoric)
                  - 0.7-0.9: Major (mobilization, direct threats)
                  - 1.0: Critical (active conflict, use of force)
        confidence: LLM's classification confidence (0.0 to 1.0, default 1.0)
        evidence_age_days: Age of event evidence in days (0 means current)
        indicator_decay_half_life_days: Optional indicator-specific temporal half-life

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
        ...     severity=0.8,  # Major event
        ...     confidence=0.95,  # High LLM confidence
        ... )
        >>> delta > 0
        True
        >>> factors.direction_multiplier
        1.0
    """
    # Validate direction
    if direction not in ("escalatory", "de_escalatory"):
        raise ValueError(f"Invalid direction: {direction}")

    # Clamp severity and confidence to valid range
    severity = max(0.0, min(1.0, severity))
    confidence = max(0.0, min(1.0, confidence))
    novelty_score = max(0.0, min(1.0, novelty_score))
    evidence_age_days = max(0.0, evidence_age_days)

    # Calculate corroboration factor
    # 1.0 score = 0.33, 4.0 score = 0.67, 9.0+ score = 1.0
    effective_corroboration = max(0.1, float(corroboration_count))
    corroboration = min(1.0, math.sqrt(effective_corroboration) / 3.0)

    if indicator_decay_half_life_days is None:
        temporal_decay_multiplier = 1.0
    else:
        half_life = max(0.1, indicator_decay_half_life_days)
        temporal_decay_multiplier = math.pow(0.5, evidence_age_days / half_life)

    # Direction multiplier
    direction_mult = 1.0 if direction == "escalatory" else -1.0

    # Calculate raw delta (now includes severity and confidence)
    raw_delta = (
        indicator_weight
        * severity  # NEW: magnitude of the signal
        * confidence  # NEW: LLM certainty
        * source_credibility
        * corroboration
        * novelty_score
        * temporal_decay_multiplier
        * direction_mult
    )

    # Clamp to prevent any single event from dominating
    clamped_delta = max(-MAX_DELTA_PER_EVENT, min(MAX_DELTA_PER_EVENT, raw_delta))

    factors = EvidenceFactors(
        base_weight=indicator_weight,
        severity=severity,
        confidence=confidence,
        credibility=source_credibility,
        corroboration=corroboration,
        novelty=novelty_score,
        evidence_age_days=evidence_age_days,
        temporal_decay_multiplier=temporal_decay_multiplier,
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

    @staticmethod
    def _definition_hash(definition: Mapping[str, Any] | Any) -> str:
        normalized_definition = definition if isinstance(definition, Mapping) else {}
        serialized = json.dumps(
            normalized_definition,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def apply_log_odds_delta(
        self,
        *,
        trend_id: UUID,
        delta: float,
        reason: str,
        trend_name: str | None = None,
        updated_at: datetime | None = None,
        fallback_current_log_odds: float | None = None,
    ) -> tuple[float, float]:
        """Apply a log-odds delta atomically and return (previous_lo, new_lo)."""
        from src.storage.models import Trend

        delta_value = Decimal(str(delta))
        applied_at = _as_utc(updated_at) if updated_at is not None else datetime.now(UTC)
        stmt = (
            update(Trend)
            .where(Trend.id == trend_id)
            .values(
                current_log_odds=Trend.current_log_odds + delta_value,
                updated_at=applied_at,
            )
            .returning(Trend.current_log_odds)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        raw_new_log_odds = result.scalar_one_or_none()
        if isawaitable(raw_new_log_odds):
            raw_new_log_odds = await raw_new_log_odds

        parsed_new_log_odds: float | None = None
        if isinstance(raw_new_log_odds, int | float | Decimal):
            parsed_new_log_odds = float(raw_new_log_odds)

        if parsed_new_log_odds is None:
            if fallback_current_log_odds is None:
                msg = f"Trend '{trend_id}' not found for atomic log-odds update"
                raise ValueError(msg)
            previous_lo = float(fallback_current_log_odds)
            new_lo = previous_lo + float(delta_value)
            logger.warning(
                "Atomic trend delta update returned no row; using in-memory fallback",
                trend_id=str(trend_id),
                trend_name=trend_name,
                delta=float(delta_value),
                reason=reason,
                update_strategy="fallback_in_memory",
            )
            return previous_lo, new_lo

        new_lo = parsed_new_log_odds
        previous_lo = new_lo - float(delta_value)
        logger.debug(
            "Applied atomic trend log-odds delta",
            trend_id=str(trend_id),
            trend_name=trend_name,
            delta=float(delta_value),
            reason=reason,
            update_strategy="atomic_sql_add",
            previous_log_odds=previous_lo,
            new_log_odds=new_lo,
        )
        return previous_lo, new_lo

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

        prior_log_odds = float(trend.current_log_odds)
        previous_prob = logodds_to_prob(prior_log_odds)

        existing = await self.session.execute(
            # Ensure idempotency: never apply the same (trend, event, signal) twice.
            # The DB enforces this with a unique constraint, but we want a clean no-op
            # return instead of "apply delta then fail on commit".
            select(TrendEvidence.id).where(
                TrendEvidence.trend_id == trend.id,
                TrendEvidence.event_id == event_id,
                TrendEvidence.signal_type == signal_type,
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info(
                "Duplicate evidence ignored (idempotent)",
                trend_id=str(trend.id),
                trend_name=trend.name,
                event_id=str(event_id),
                signal_type=signal_type,
            )
            return TrendUpdate(
                previous_probability=previous_prob,
                new_probability=previous_prob,
                delta_applied=0.0,
                direction="unchanged",
            )

        # Get previous probability
        evidence = TrendEvidence(
            trend_id=trend.id,
            event_id=event_id,
            signal_type=signal_type,
            base_weight=factors.base_weight,
            direction_multiplier=factors.direction_multiplier,
            trend_definition_hash=self._definition_hash(trend.definition),
            credibility_score=factors.credibility,
            corroboration_factor=factors.corroboration,
            novelty_score=factors.novelty,
            evidence_age_days=factors.evidence_age_days,
            temporal_decay_factor=factors.temporal_decay_multiplier,
            severity_score=factors.severity,
            confidence_score=factors.confidence,
            delta_log_odds=delta,
            reasoning=reasoning,
        )

        try:
            async with self.session.begin_nested():
                self.session.add(evidence)
                await self.session.flush()
        except IntegrityError:
            # Another worker inserted the same evidence concurrently.
            logger.info(
                "Evidence insert raced; treated as duplicate (idempotent)",
                trend_id=str(trend.id),
                trend_name=trend.name,
                event_id=str(event_id),
                signal_type=signal_type,
            )
            return TrendUpdate(
                previous_probability=previous_prob,
                new_probability=previous_prob,
                delta_applied=0.0,
                direction="unchanged",
            )

        # Apply delta only after evidence record is guaranteed unique/persistable.
        applied_at = datetime.now(UTC)
        previous_lo, new_lo = await self.apply_log_odds_delta(
            trend_id=trend.id,
            trend_name=trend.name,
            delta=delta,
            reason="evidence",
            updated_at=applied_at,
            fallback_current_log_odds=prior_log_odds,
        )
        trend.current_log_odds = new_lo
        trend.updated_at = applied_at

        previous_prob = logodds_to_prob(previous_lo)
        new_prob = logodds_to_prob(new_lo)

        # Determine direction
        if delta > 0.001:
            direction = "up"
        elif delta < -0.001:
            direction = "down"
        else:
            direction = "unchanged"

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
            new_lo = baseline_lo + (current_lo - baseline_lo) * decay_factor

        Where decay_factor = 0.5^(days_elapsed / half_life)

        This means after one half-life, the deviation from baseline
        is reduced by 50%. After two half-lives, 75%, etc.

        Args:
            trend: Trend to decay
            as_of: Reference time (default: now)

        Returns:
            New probability after decay
        """
        as_of = _as_utc(as_of) if as_of is not None else datetime.now(UTC)

        from src.storage.models import Trend as TrendModel

        locked_row_result = await self.session.execute(
            select(
                TrendModel.current_log_odds.label("current_log_odds"),
                TrendModel.baseline_log_odds.label("baseline_log_odds"),
                TrendModel.updated_at.label("updated_at"),
                TrendModel.decay_half_life_days.label("decay_half_life_days"),
            )
            .where(TrendModel.id == trend.id)
            .with_for_update()
        )
        raw_locked_row: Any = locked_row_result.one_or_none()
        if isawaitable(raw_locked_row):
            raw_locked_row = await raw_locked_row

        row_mapping = getattr(raw_locked_row, "_mapping", None)
        typed_mapping: Mapping[str, Any] | None = (
            row_mapping if isinstance(row_mapping, Mapping) else None
        )
        has_locked_state = (
            typed_mapping is not None
            and typed_mapping.get("current_log_odds") is not None
            and typed_mapping.get("baseline_log_odds") is not None
            and isinstance(typed_mapping.get("updated_at"), datetime)
        )
        if has_locked_state and typed_mapping is not None:
            current_lo = float(typed_mapping["current_log_odds"])
            baseline_lo = float(typed_mapping["baseline_log_odds"])
            last_updated_at = _as_utc(typed_mapping["updated_at"])
            half_life = typed_mapping["decay_half_life_days"] or DEFAULT_DECAY_HALF_LIFE_DAYS
        else:
            current_lo = float(trend.current_log_odds)
            baseline_lo = float(trend.baseline_log_odds)
            last_updated_at = _as_utc(trend.updated_at)
            half_life = trend.decay_half_life_days or DEFAULT_DECAY_HALF_LIFE_DAYS

        days_elapsed = (as_of - last_updated_at).total_seconds() / 86400.0
        if days_elapsed <= 0:
            trend.current_log_odds = current_lo
            trend.updated_at = last_updated_at
            return logodds_to_prob(current_lo)

        decay_factor = math.pow(0.5, days_elapsed / half_life)
        deviation = current_lo - baseline_lo
        new_lo = baseline_lo + (deviation * decay_factor)

        if has_locked_state:
            await self.session.execute(
                update(TrendModel)
                .where(TrendModel.id == trend.id)
                .values(current_log_odds=new_lo, updated_at=as_of)
                .execution_options(synchronize_session=False)
            )
        trend.current_log_odds = new_lo
        trend.updated_at = as_of

        new_prob = logodds_to_prob(new_lo)

        logger.debug(
            "Decay applied to trend",
            trend_id=str(trend.id),
            trend_name=trend.name,
            days_elapsed=days_elapsed,
            decay_factor=decay_factor,
            previous_lo=current_lo,
            new_lo=new_lo,
            new_prob=new_prob,
            update_strategy=("row_lock_serialized" if has_locked_state else "fallback_in_memory"),
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

        at = _as_utc(at)

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
            datetime.now(UTC) - timedelta(days=days),
        )

        if past is None:
            return "stable"  # Not enough history

        delta = current - past

        if delta >= 0.05:
            return "rising_fast"
        if delta >= 0.01:
            return "rising"
        if delta <= -0.05:
            return "falling_fast"
        if delta <= -0.01:
            return "falling"
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
            datetime.now(UTC) - timedelta(days=days),
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

        cutoff = datetime.now(UTC) - timedelta(days=days)

        result = await self.session.execute(
            select(TrendEvidence)
            .where(TrendEvidence.trend_id == trend_id)
            .where(TrendEvidence.created_at >= cutoff)
            .where(TrendEvidence.is_invalidated.is_(False))
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
