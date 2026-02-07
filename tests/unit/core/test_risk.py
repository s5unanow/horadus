from __future__ import annotations

import pytest

from src.core.risk import (
    ConfidenceRating,
    calculate_probability_band,
    get_confidence_rating,
    get_risk_level,
)
from src.storage.models import RiskLevel

pytestmark = pytest.mark.unit


def test_get_risk_level_thresholds() -> None:
    assert get_risk_level(0.05) == RiskLevel.LOW
    assert get_risk_level(0.10) == RiskLevel.GUARDED
    assert get_risk_level(0.30) == RiskLevel.ELEVATED
    assert get_risk_level(0.60) == RiskLevel.HIGH
    assert get_risk_level(0.90) == RiskLevel.SEVERE


def test_calculate_probability_band_more_evidence_narrows_band() -> None:
    low_evidence = calculate_probability_band(
        probability=0.5,
        evidence_count_30d=2,
        avg_corroboration=0.4,
        days_since_last_evidence=10,
    )
    high_evidence = calculate_probability_band(
        probability=0.5,
        evidence_count_30d=50,
        avg_corroboration=0.9,
        days_since_last_evidence=1,
    )

    low_width = low_evidence[1] - low_evidence[0]
    high_width = high_evidence[1] - high_evidence[0]
    assert high_width < low_width


def test_calculate_probability_band_clamps_bounds() -> None:
    lower_band = calculate_probability_band(
        probability=0.02,
        evidence_count_30d=0,
        avg_corroboration=0.2,
        days_since_last_evidence=45,
    )
    upper_band = calculate_probability_band(
        probability=0.98,
        evidence_count_30d=0,
        avg_corroboration=0.2,
        days_since_last_evidence=45,
    )

    assert lower_band[0] >= 0.001
    assert upper_band[1] <= 0.999


def test_get_confidence_rating_bands() -> None:
    low = get_confidence_rating(
        band_width=0.35,
        evidence_count=1,
        avg_corroboration=0.3,
    )
    medium = get_confidence_rating(
        band_width=0.18,
        evidence_count=7,
        avg_corroboration=0.5,
    )
    high = get_confidence_rating(
        band_width=0.08,
        evidence_count=25,
        avg_corroboration=0.8,
    )

    assert low == ConfidenceRating.LOW
    assert medium == ConfidenceRating.MEDIUM
    assert high == ConfidenceRating.HIGH
