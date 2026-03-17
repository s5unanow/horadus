"""Shared comparison helpers for reconciled trend-evidence rows."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_FLOAT_TOLERANCE = 1e-6


def _evidence_matches(evidence: Any, desired: Any, *, desired_hash: str) -> bool:
    return (
        evidence.trend_definition_hash == desired_hash
        and _float_matches(evidence.base_weight, desired.factors.base_weight, places=6)
        and _float_matches(
            evidence.direction_multiplier, desired.factors.direction_multiplier, places=1
        )
        and _float_matches(evidence.credibility_score, desired.factors.credibility, places=2)
        and _float_matches(evidence.corroboration_factor, desired.factors.corroboration, places=2)
        and _float_matches(evidence.novelty_score, desired.factors.novelty, places=2)
        and _float_matches(evidence.evidence_age_days, desired.factors.evidence_age_days, places=2)
        and _float_matches(
            evidence.temporal_decay_factor,
            desired.factors.temporal_decay_multiplier,
            places=4,
        )
        and _float_matches(evidence.severity_score, desired.factors.severity, places=2)
        and _float_matches(evidence.confidence_score, desired.factors.confidence, places=2)
        and _float_matches(evidence.delta_log_odds, desired.delta, places=6)
        and (evidence.reasoning or None) == desired.reasoning
    )


def _float_matches(left: Any, right: Any, *, places: int | None = None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if places is not None:
        return _quantize_float(left, places=places) == _quantize_float(right, places=places)
    return abs(float(left) - float(right)) <= _FLOAT_TOLERANCE


def _quantize_float(value: Any, *, places: int) -> Decimal:
    quantum = Decimal("1").scaleb(-places)
    return Decimal(str(float(value))).quantize(quantum, rounding=ROUND_HALF_UP)
