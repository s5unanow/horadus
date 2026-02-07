"""
Source credibility helpers with tier/reporting multipliers.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import case

from src.storage.models import ReportingType, SourceTier

DEFAULT_SOURCE_CREDIBILITY = 0.5

TIER_MULTIPLIERS: dict[str, float] = {
    SourceTier.PRIMARY.value: 1.0,
    SourceTier.WIRE.value: 0.95,
    SourceTier.MAJOR.value: 0.85,
    SourceTier.REGIONAL.value: 0.70,
    SourceTier.AGGREGATOR.value: 0.50,
}

REPORTING_MULTIPLIERS: dict[str, float] = {
    ReportingType.FIRSTHAND.value: 1.0,
    ReportingType.SECONDARY.value: 0.70,
    ReportingType.AGGREGATOR.value: 0.40,
}


def tier_multiplier(source_tier: str | None) -> float:
    """Return credibility multiplier for a source tier."""
    if source_tier is None:
        return 1.0
    return TIER_MULTIPLIERS.get(source_tier, 1.0)


def reporting_multiplier(reporting_type: str | None) -> float:
    """Return credibility multiplier for reporting type."""
    if reporting_type is None:
        return 1.0
    return REPORTING_MULTIPLIERS.get(reporting_type, 1.0)


def effective_source_credibility(
    *,
    base_credibility: Any,
    source_tier: str | None,
    reporting_type: str | None,
) -> float:
    """Apply source tier and reporting multipliers to base credibility."""
    try:
        base = float(base_credibility)
    except (TypeError, ValueError):
        base = DEFAULT_SOURCE_CREDIBILITY

    adjusted = base * tier_multiplier(source_tier) * reporting_multiplier(reporting_type)
    if adjusted < 0.0:
        return 0.0
    if adjusted > 1.0:
        return 1.0
    return adjusted


def source_multiplier_expression(*, source_tier_col: Any, reporting_type_col: Any) -> Any:
    """
    Build SQL expression for source credibility multiplier.

    Unknown tiers/types intentionally default to multiplier 1.0.
    """
    tier_expr = case(
        (source_tier_col == SourceTier.PRIMARY.value, 1.0),
        (source_tier_col == SourceTier.WIRE.value, 0.95),
        (source_tier_col == SourceTier.MAJOR.value, 0.85),
        (source_tier_col == SourceTier.REGIONAL.value, 0.70),
        (source_tier_col == SourceTier.AGGREGATOR.value, 0.50),
        else_=1.0,
    )
    reporting_expr = case(
        (reporting_type_col == ReportingType.FIRSTHAND.value, 1.0),
        (reporting_type_col == ReportingType.SECONDARY.value, 0.70),
        (reporting_type_col == ReportingType.AGGREGATOR.value, 0.40),
        else_=1.0,
    )
    return tier_expr * reporting_expr
