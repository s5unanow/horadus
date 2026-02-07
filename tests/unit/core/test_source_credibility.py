from __future__ import annotations

import pytest

from src.core.source_credibility import (
    DEFAULT_SOURCE_CREDIBILITY,
    effective_source_credibility,
    reporting_multiplier,
    tier_multiplier,
)
from src.storage.models import ReportingType, SourceTier

pytestmark = pytest.mark.unit


def test_tier_multiplier_uses_expected_weights() -> None:
    assert tier_multiplier(SourceTier.PRIMARY.value) == pytest.approx(1.0)
    assert tier_multiplier(SourceTier.WIRE.value) == pytest.approx(0.95)
    assert tier_multiplier(SourceTier.MAJOR.value) == pytest.approx(0.85)
    assert tier_multiplier(SourceTier.REGIONAL.value) == pytest.approx(0.70)
    assert tier_multiplier(SourceTier.AGGREGATOR.value) == pytest.approx(0.50)


def test_reporting_multiplier_uses_expected_weights() -> None:
    assert reporting_multiplier(ReportingType.FIRSTHAND.value) == pytest.approx(1.0)
    assert reporting_multiplier(ReportingType.SECONDARY.value) == pytest.approx(0.70)
    assert reporting_multiplier(ReportingType.AGGREGATOR.value) == pytest.approx(0.40)


def test_effective_source_credibility_applies_both_multipliers() -> None:
    value = effective_source_credibility(
        base_credibility=0.9,
        source_tier=SourceTier.MAJOR.value,
        reporting_type=ReportingType.SECONDARY.value,
    )
    assert value == pytest.approx(0.9 * 0.85 * 0.70)


def test_effective_source_credibility_defaults_unknown_classification_to_no_penalty() -> None:
    value = effective_source_credibility(
        base_credibility=0.8,
        source_tier="unknown-tier",
        reporting_type="unknown-reporting",
    )
    assert value == pytest.approx(0.8)


def test_effective_source_credibility_falls_back_for_invalid_base_value() -> None:
    value = effective_source_credibility(
        base_credibility="not-a-number",
        source_tier=SourceTier.WIRE.value,
        reporting_type=ReportingType.FIRSTHAND.value,
    )
    assert value == pytest.approx(DEFAULT_SOURCE_CREDIBILITY * 0.95)
