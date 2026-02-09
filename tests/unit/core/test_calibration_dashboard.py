from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.calibration_dashboard import CalibrationBucketSummary, CalibrationDashboardService

pytestmark = pytest.mark.unit


def test_render_ascii_sparkline_returns_flat_line_for_constant_values() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    assert service._render_ascii_sparkline([0.2, 0.2, 0.2]) == "---"


def test_render_ascii_sparkline_returns_varying_chars_for_changes() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    chart = service._render_ascii_sparkline([0.1, 0.25, 0.4, 0.3])
    assert len(chart) == 4
    assert len(set(chart)) > 1


def test_build_reliability_notes_formats_bucket_statement() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    notes = service._build_reliability_notes(
        [
            CalibrationBucketSummary(
                bucket_start=0.2,
                bucket_end=0.3,
                prediction_count=7,
                actual_rate=0.43,
                expected_rate=0.25,
                calibration_error=0.18,
            )
        ]
    )
    assert notes == ["When we predicted 20%-30%, it happened 43% of the time (n=7)."]


def test_build_drift_alerts_returns_warning_and_critical_entries() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    alerts = service._build_drift_alerts(
        calibration_curve=[
            CalibrationBucketSummary(
                bucket_start=0.2,
                bucket_end=0.3,
                prediction_count=9,
                actual_rate=0.56,
                expected_rate=0.25,
                calibration_error=0.31,
            )
        ],
        mean_brier_score=0.32,
        resolved_predictions=25,
    )

    assert len(alerts) == 2
    assert alerts[0].alert_type == "mean_brier_drift"
    assert alerts[0].severity == "critical"
    assert alerts[1].alert_type == "bucket_error_drift"
    assert alerts[1].severity == "critical"


def test_build_drift_alerts_skips_when_sample_size_is_too_low() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    alerts = service._build_drift_alerts(
        calibration_curve=[
            CalibrationBucketSummary(
                bucket_start=0.7,
                bucket_end=0.8,
                prediction_count=2,
                actual_rate=1.0,
                expected_rate=0.75,
                calibration_error=0.25,
            )
        ],
        mean_brier_score=0.35,
        resolved_predictions=5,
    )
    assert alerts == []
