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
