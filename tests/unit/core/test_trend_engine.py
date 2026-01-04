"""
Unit tests for the Trend Engine.

Tests probability conversion, evidence calculation, and trend updates.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.trend_engine import (
    MAX_DELTA_PER_EVENT,
    MAX_PROBABILITY,
    MIN_PROBABILITY,
    EvidenceFactors,
    TrendEngine,
    TrendUpdate,
    calculate_evidence_delta,
    format_direction,
    format_probability,
    logodds_to_prob,
    prob_to_logodds,
)

# =============================================================================
# Probability Conversion Tests
# =============================================================================


class TestProbToLogodds:
    """Tests for prob_to_logodds function."""

    def test_half_probability_gives_zero(self):
        """p=0.5 should give log-odds of 0."""
        assert prob_to_logodds(0.5) == pytest.approx(0.0)

    def test_low_probability_gives_negative(self):
        """Low probability should give negative log-odds."""
        assert prob_to_logodds(0.1) < 0
        assert prob_to_logodds(0.01) < prob_to_logodds(0.1)

    def test_high_probability_gives_positive(self):
        """High probability should give positive log-odds."""
        assert prob_to_logodds(0.9) > 0
        assert prob_to_logodds(0.99) > prob_to_logodds(0.9)

    def test_symmetry(self):
        """p and 1-p should have opposite log-odds."""
        for p in [0.1, 0.2, 0.3, 0.4]:
            lo_low = prob_to_logodds(p)
            lo_high = prob_to_logodds(1 - p)
            assert lo_low == pytest.approx(-lo_high, rel=1e-6)

    def test_zero_probability_clamped(self):
        """p=0 should be clamped to MIN_PROBABILITY."""
        lo = prob_to_logodds(0.0)
        assert lo == prob_to_logodds(MIN_PROBABILITY)

    def test_one_probability_clamped(self):
        """p=1 should be clamped to MAX_PROBABILITY."""
        lo = prob_to_logodds(1.0)
        assert lo == prob_to_logodds(MAX_PROBABILITY)

    def test_known_values(self):
        """Test against known log-odds values."""
        # p=0.1 -> log(0.1/0.9) = log(1/9) ≈ -2.197
        assert prob_to_logodds(0.1) == pytest.approx(-2.197, rel=0.01)
        # p=0.9 -> log(0.9/0.1) = log(9) ≈ 2.197
        assert prob_to_logodds(0.9) == pytest.approx(2.197, rel=0.01)


class TestLogoddsToProb:
    """Tests for logodds_to_prob function."""

    def test_zero_gives_half(self):
        """Log-odds of 0 should give p=0.5."""
        assert logodds_to_prob(0.0) == pytest.approx(0.5)

    def test_negative_gives_low_probability(self):
        """Negative log-odds should give p < 0.5."""
        assert logodds_to_prob(-1) < 0.5
        assert logodds_to_prob(-2) < logodds_to_prob(-1)

    def test_positive_gives_high_probability(self):
        """Positive log-odds should give p > 0.5."""
        assert logodds_to_prob(1) > 0.5
        assert logodds_to_prob(2) > logodds_to_prob(1)

    def test_extreme_negative_clamped(self):
        """Very negative log-odds should clamp to MIN_PROBABILITY."""
        assert logodds_to_prob(-1000) == MIN_PROBABILITY

    def test_extreme_positive_clamped(self):
        """Very positive log-odds should clamp to MAX_PROBABILITY."""
        assert logodds_to_prob(1000) == MAX_PROBABILITY

    def test_inverse_of_prob_to_logodds(self):
        """Converting back and forth should preserve value."""
        for p in [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]:
            lo = prob_to_logodds(p)
            recovered = logodds_to_prob(lo)
            assert recovered == pytest.approx(p, rel=1e-6)


# =============================================================================
# Evidence Calculation Tests
# =============================================================================


class TestCalculateEvidenceDelta:
    """Tests for calculate_evidence_delta function."""

    def test_escalatory_gives_positive_delta(self):
        """Escalatory evidence should produce positive delta."""
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

    def test_deescalatory_gives_negative_delta(self):
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

    def test_invalid_direction_raises(self):
        """Invalid direction should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid direction"):
            calculate_evidence_delta(
                signal_type="test",
                indicator_weight=0.04,
                source_credibility=0.9,
                corroboration_count=1,
                novelty_score=1.0,
                direction="invalid",
            )

    def test_corroboration_scaling(self):
        """More sources should increase corroboration factor."""
        _, factors_1 = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
        )
        _, factors_4 = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=4,
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

        assert factors_1.corroboration < factors_4.corroboration
        assert factors_4.corroboration < factors_9.corroboration
        # 9 sources should cap at 1.0
        assert factors_9.corroboration == pytest.approx(1.0)

    def test_corroboration_formula(self):
        """Verify corroboration formula: sqrt(n) / 3."""
        _, factors = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=4,
            novelty_score=1.0,
            direction="escalatory",
        )
        # sqrt(4) / 3 = 2/3 ≈ 0.667
        assert factors.corroboration == pytest.approx(2 / 3, rel=0.01)

    def test_credibility_affects_delta(self):
        """Higher credibility should produce larger delta."""
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
        """Higher novelty should produce larger delta."""
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
        # Should be proportional
        assert abs(delta_new) / abs(delta_old) == pytest.approx(1.0 / 0.3, rel=0.01)

    def test_severity_affects_delta(self):
        """Higher severity (magnitude) should produce larger delta."""
        delta_major, factors_major = calculate_evidence_delta(
            signal_type="military_movement",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
            severity=0.9,  # Major event
        )
        delta_routine, factors_routine = calculate_evidence_delta(
            signal_type="military_movement",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
            severity=0.2,  # Routine event
        )
        assert abs(delta_major) > abs(delta_routine)
        assert factors_major.severity == 0.9
        assert factors_routine.severity == 0.2
        # Should be proportional
        assert abs(delta_major) / abs(delta_routine) == pytest.approx(0.9 / 0.2, rel=0.01)

    def test_confidence_affects_delta(self):
        """Higher LLM confidence should produce larger delta."""
        delta_confident, factors_high = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
            confidence=0.95,  # High confidence
        )
        delta_uncertain, factors_low = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
            confidence=0.5,  # Uncertain
        )
        assert abs(delta_confident) > abs(delta_uncertain)
        assert factors_high.confidence == 0.95
        assert factors_low.confidence == 0.5

    def test_severity_and_confidence_combined(self):
        """Test that severity and confidence multiply together."""
        # Baseline: no severity/confidence multipliers (defaults to 1.0)
        delta_full, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
            severity=1.0,
            confidence=1.0,
        )
        # With severity=0.5 and confidence=0.5, should be 0.25x
        delta_reduced, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
            severity=0.5,
            confidence=0.5,
        )
        assert abs(delta_reduced) / abs(delta_full) == pytest.approx(0.25, rel=0.01)

    def test_delta_clamped_to_max(self):
        """Extreme inputs should be clamped to MAX_DELTA_PER_EVENT."""
        delta, factors = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=10.0,  # Unrealistically high
            source_credibility=1.0,
            corroboration_count=100,
            novelty_score=1.0,
            direction="escalatory",
        )
        assert delta == MAX_DELTA_PER_EVENT
        assert factors.raw_delta != factors.clamped_delta

    def test_negative_delta_clamped(self):
        """Negative delta should also be clamped."""
        delta, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=10.0,
            source_credibility=1.0,
            corroboration_count=100,
            novelty_score=1.0,
            direction="de_escalatory",
        )
        assert delta == -MAX_DELTA_PER_EVENT

    def test_factors_breakdown(self):
        """Verify factors are correctly recorded."""
        delta, factors = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.05,
            source_credibility=0.8,
            corroboration_count=4,
            novelty_score=0.5,
            direction="escalatory",
        )
        assert factors.base_weight == 0.05
        assert factors.credibility == 0.8
        assert factors.novelty == 0.5
        assert factors.direction_multiplier == 1.0
        assert factors.clamped_delta == delta


# =============================================================================
# Trend Engine Tests
# =============================================================================


class TestTrendEngine:
    """Tests for TrendEngine class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Default: no existing evidence found.
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)

        @asynccontextmanager
        async def _begin_nested():
            yield

        session.begin_nested = MagicMock(return_value=_begin_nested())
        return session

    @pytest.fixture
    def mock_trend(self):
        """Create a mock trend object."""
        trend = MagicMock()
        trend.id = uuid4()
        trend.name = "Test Trend"
        trend.current_log_odds = 0.0  # 50% probability
        trend.updated_at = datetime.now(UTC)
        trend.decay_half_life_days = 30
        trend.definition = {"baseline_probability": 0.1}
        return trend

    @pytest.fixture
    def sample_factors(self):
        """Create sample evidence factors."""
        return EvidenceFactors(
            base_weight=0.04,
            severity=0.8,
            confidence=0.95,
            credibility=0.9,
            corroboration=0.67,
            novelty=1.0,
            direction_multiplier=1.0,
            raw_delta=0.024,
            clamped_delta=0.024,
        )

    def test_get_probability(self, mock_session, mock_trend):
        """Test getting current probability."""
        engine = TrendEngine(mock_session)

        mock_trend.current_log_odds = 0.0
        assert engine.get_probability(mock_trend) == pytest.approx(0.5)

        mock_trend.current_log_odds = prob_to_logodds(0.25)
        assert engine.get_probability(mock_trend) == pytest.approx(0.25, rel=0.01)

    @pytest.mark.asyncio
    async def test_apply_evidence_updates_logodds(self, mock_session, mock_trend, sample_factors):
        """Test that apply_evidence updates trend log-odds."""
        engine = TrendEngine(mock_session)

        initial_lo = mock_trend.current_log_odds
        delta = 0.1

        result = await engine.apply_evidence(
            trend=mock_trend,
            delta=delta,
            event_id=uuid4(),
            signal_type="military_movement",
            factors=sample_factors,
            reasoning="Test reasoning",
        )

        assert mock_trend.current_log_odds == initial_lo + delta
        assert result.delta_applied == delta

    @pytest.mark.asyncio
    async def test_apply_evidence_returns_update(self, mock_session, mock_trend, sample_factors):
        """Test that apply_evidence returns correct TrendUpdate."""
        engine = TrendEngine(mock_session)

        mock_trend.current_log_odds = 0.0  # 50%
        delta = 0.2  # Should increase probability

        result = await engine.apply_evidence(
            trend=mock_trend,
            delta=delta,
            event_id=uuid4(),
            signal_type="test",
            factors=sample_factors,
            reasoning="Test",
        )

        assert isinstance(result, TrendUpdate)
        assert result.previous_probability == pytest.approx(0.5)
        assert result.new_probability > result.previous_probability
        assert result.direction == "up"

    @pytest.mark.asyncio
    async def test_apply_evidence_creates_record(self, mock_session, mock_trend, sample_factors):
        """Test that apply_evidence creates evidence record."""
        engine = TrendEngine(mock_session)

        await engine.apply_evidence(
            trend=mock_trend,
            delta=0.1,
            event_id=uuid4(),
            signal_type="test",
            factors=sample_factors,
            reasoning="Test reasoning",
        )

        # Should have called session.add with an evidence record
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_evidence_duplicate_is_noop(self, mock_session, mock_trend, sample_factors):
        """Duplicate (trend,event,signal) evidence should not re-apply delta."""
        engine = TrendEngine(mock_session)

        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = uuid4()
        mock_session.execute = AsyncMock(return_value=execute_result)

        initial_lo = mock_trend.current_log_odds
        result = await engine.apply_evidence(
            trend=mock_trend,
            delta=0.5,
            event_id=uuid4(),
            signal_type="test",
            factors=sample_factors,
            reasoning="Test reasoning",
        )

        assert mock_trend.current_log_odds == initial_lo
        assert result.delta_applied == 0.0
        assert result.direction == "unchanged"
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_evidence_race_integrityerror_is_noop(
        self, mock_session, mock_trend, sample_factors
    ):
        """If evidence insert races, treat it as idempotent and don't apply delta."""
        engine = TrendEngine(mock_session)

        # No existing evidence found in the pre-check.
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=execute_result)

        mock_session.flush.side_effect = IntegrityError("stmt", {}, Exception("boom"))

        initial_lo = mock_trend.current_log_odds
        result = await engine.apply_evidence(
            trend=mock_trend,
            delta=0.5,
            event_id=uuid4(),
            signal_type="test",
            factors=sample_factors,
            reasoning="Test reasoning",
        )

        assert mock_trend.current_log_odds == initial_lo
        assert result.delta_applied == 0.0
        assert result.direction == "unchanged"

    @pytest.mark.asyncio
    async def test_apply_decay_moves_toward_baseline(self, mock_session, mock_trend):
        """Test that decay moves probability toward baseline."""
        engine = TrendEngine(mock_session)

        # Start at 50% (log-odds = 0), baseline is 10%
        mock_trend.current_log_odds = 0.0
        mock_trend.updated_at = datetime.now(UTC) - timedelta(days=30)  # One half-life

        new_prob = await engine.apply_decay(mock_trend)

        # After one half-life, should be halfway between 50% and 10%
        # In log-odds space: 0 + (lo(0.1) - 0) * 0.5
        baseline_lo = prob_to_logodds(0.1)
        expected_lo = baseline_lo + (0 - baseline_lo) * 0.5
        expected_prob = logodds_to_prob(expected_lo)

        assert new_prob == pytest.approx(expected_prob, rel=0.01)

    @pytest.mark.asyncio
    async def test_apply_decay_no_change_if_recent(self, mock_session, mock_trend):
        """Test that decay has no effect if just updated."""
        engine = TrendEngine(mock_session)

        mock_trend.current_log_odds = 0.5
        mock_trend.updated_at = datetime.now(UTC)  # Just now

        original_lo = mock_trend.current_log_odds
        await engine.apply_decay(mock_trend)

        # Should be unchanged
        assert mock_trend.current_log_odds == pytest.approx(original_lo, rel=0.001)


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_format_probability(self):
        """Test probability formatting."""
        assert format_probability(0.5) == "50.0%"
        assert format_probability(0.123) == "12.3%"
        assert format_probability(0.999) == "99.9%"
        assert format_probability(0.001) == "0.1%"
        assert format_probability(0.5, precision=0) == "50%"
        assert format_probability(0.5, precision=2) == "50.00%"

    def test_format_direction(self):
        """Test direction formatting."""
        assert "Rising Fast" in format_direction("rising_fast")
        assert "Rising" in format_direction("rising")
        assert "Stable" in format_direction("stable")
        assert "Falling" in format_direction("falling")
        assert "Falling Fast" in format_direction("falling_fast")


# =============================================================================
# Integration Tests
# =============================================================================


class TestEvidenceIntegration:
    """Integration tests for evidence calculation and application."""

    def test_realistic_scenario(self):
        """Test a realistic evidence scenario."""
        # Scenario: Multiple credible sources report military movement
        delta, _factors = calculate_evidence_delta(
            signal_type="military_movement",
            indicator_weight=0.04,  # From trend config
            source_credibility=0.95,  # Reuters
            corroboration_count=5,  # 5 independent sources
            novelty_score=1.0,  # New information
            direction="escalatory",
        )

        # Delta should be meaningful but not extreme
        assert 0.01 < delta < 0.1

        # Apply to a trend at 10% baseline
        initial_prob = 0.10
        initial_lo = prob_to_logodds(initial_prob)
        new_lo = initial_lo + delta
        new_prob = logodds_to_prob(new_lo)

        # Should increase probability modestly
        assert new_prob > initial_prob
        assert new_prob < 0.20  # But not by too much

    def test_low_credibility_low_impact(self):
        """Test that low-credibility sources have low impact."""
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

        # Low credibility should have roughly 1/3 the impact
        ratio = delta_low / delta_high
        assert ratio == pytest.approx(0.30 / 0.95, rel=0.01)

    def test_repeated_news_has_less_impact(self):
        """Test that repeated news has less impact than new news."""
        delta_new, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=1.0,
            direction="escalatory",
        )
        delta_repeat, _ = calculate_evidence_delta(
            signal_type="test",
            indicator_weight=0.04,
            source_credibility=0.9,
            corroboration_count=1,
            novelty_score=0.3,
            direction="escalatory",
        )

        assert delta_repeat < delta_new
        assert delta_repeat / delta_new == pytest.approx(0.3, rel=0.01)
