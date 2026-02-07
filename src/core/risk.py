"""
Risk-level and probability-band presentation helpers.
"""

from __future__ import annotations

import enum

from src.storage.models import RiskLevel


class ConfidenceRating(enum.StrEnum):
    """Confidence rating for probability presentations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def get_risk_level(probability: float) -> RiskLevel:
    """Map probability to categorical risk level."""
    if probability < 0.10:
        return RiskLevel.LOW
    if probability < 0.25:
        return RiskLevel.GUARDED
    if probability < 0.50:
        return RiskLevel.ELEVATED
    if probability < 0.75:
        return RiskLevel.HIGH
    return RiskLevel.SEVERE


def calculate_probability_band(
    *,
    probability: float,
    evidence_count_30d: int,
    avg_corroboration: float,
    days_since_last_evidence: int,
) -> tuple[float, float]:
    """
    Calculate a confidence interval around probability.

    More evidence and better corroboration narrow the band.
    Older evidence widens the band.
    """
    base_uncertainty = 0.15
    volume_factor = max(0.3, 1.0 - (evidence_count_30d / 50))
    recency_factor = min(2.0, 1.0 + (days_since_last_evidence / 30))
    corroboration_factor = max(0.5, 1.5 - avg_corroboration)

    uncertainty = base_uncertainty * volume_factor * recency_factor * corroboration_factor
    lower = max(0.001, probability - uncertainty)
    upper = min(0.999, probability + uncertainty)
    return lower, upper


def get_confidence_rating(
    *,
    band_width: float,
    evidence_count: int,
    avg_corroboration: float,
) -> ConfidenceRating:
    """Classify confidence from band width and evidence quality."""
    score = 0

    if band_width < 0.10:
        score += 2
    elif band_width < 0.20:
        score += 1

    if evidence_count >= 20:
        score += 2
    elif evidence_count >= 5:
        score += 1

    if avg_corroboration >= 0.7:
        score += 1

    if score >= 4:
        return ConfidenceRating.HIGH
    if score >= 2:
        return ConfidenceRating.MEDIUM
    return ConfidenceRating.LOW
