from __future__ import annotations

import pytest

from src.eval import benchmark as benchmark_module

pytestmark = pytest.mark.unit


def test_tier2_metrics_records_schema_runtime_failures() -> None:
    metrics = benchmark_module._Tier2Metrics()
    expected = benchmark_module.Tier2GoldLabel(
        trend_id="eu-russia",
        signal_type="military_movement",
        direction="escalatory",
        severity=0.7,
        confidence=0.8,
    )

    metrics.record(expected=expected, predicted=None, failure_stage="schema_runtime")

    assert metrics.to_dict()["schema_runtime_failures"] == 1


def test_tier2_failure_stage_classifies_schema_runtime_errors() -> None:
    assert (
        benchmark_module._tier2_failure_stage(
            error_category="ValidationError",
            error_message="bad model payload",
        )
        == "schema_runtime"
    )
    assert (
        benchmark_module._tier2_failure_stage(
            error_category="ValueError",
            error_message="Invalid isoformat string: '2025-ish'",
        )
        == "schema_runtime"
    )
