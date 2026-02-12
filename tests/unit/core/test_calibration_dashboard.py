from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.calibration_dashboard import (
    CalibrationBucketSummary,
    CalibrationCoverageSummary,
    CalibrationDashboardService,
    CalibrationDriftAlert,
    TrendCoverageSummary,
)

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
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=25,
        resolved_predictions=25,
        unresolved_predictions=0,
        overall_resolved_ratio=1.0,
        trends_with_predictions=2,
        trends_meeting_min=2,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=True,
    )
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
        coverage=coverage,
    )

    assert len(alerts) == 2
    assert alerts[0].alert_type == "mean_brier_drift"
    assert alerts[0].severity == "critical"
    assert alerts[1].alert_type == "bucket_error_drift"
    assert alerts[1].severity == "critical"


def test_build_drift_alerts_skips_when_sample_size_is_too_low() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=5,
        resolved_predictions=5,
        unresolved_predictions=0,
        overall_resolved_ratio=1.0,
        trends_with_predictions=1,
        trends_meeting_min=1,
        trends_below_min=0,
        low_sample_trends=[],
        coverage_sufficient=True,
    )
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
        coverage=coverage,
    )
    assert alerts == []


def test_build_coverage_summary_marks_low_sample_trends() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    summary = service._build_coverage_summary(
        total_by_trend={},
        resolved_by_trend={},
        trend_name_by_id={},
    )
    assert summary.coverage_sufficient is False
    assert summary.total_predictions == 0


def test_build_coverage_alerts_emits_low_sample_warning() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    coverage = CalibrationCoverageSummary(
        min_resolved_per_trend=5,
        min_resolved_ratio=0.5,
        total_predictions=8,
        resolved_predictions=3,
        unresolved_predictions=5,
        overall_resolved_ratio=0.375,
        trends_with_predictions=1,
        trends_meeting_min=0,
        trends_below_min=1,
        low_sample_trends=[
            TrendCoverageSummary(
                trend_id=uuid4(),
                trend_name="EU-Russia",
                total_predictions=8,
                resolved_predictions=3,
                resolved_ratio=0.375,
            )
        ],
        coverage_sufficient=False,
    )
    alerts = service._build_coverage_alerts(coverage)
    assert alerts
    assert alerts[0].alert_type == "low_sample_coverage"


def test_build_reliability_summary_aggregates_source_metrics() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    outcome_id_one = uuid4()
    outcome_id_two = uuid4()
    outcome_id_three = uuid4()

    summary = service._build_reliability_summary_from_pairs(
        dimension="source",
        min_sample_size=2,
        pairs=[
            ("source-a", "Reuters", outcome_id_one),
            ("source-a", "Reuters", outcome_id_two),
            ("source-b", "AP", outcome_id_three),
        ],
        outcome_metrics={
            outcome_id_one: (0.8, 1.0, 0.04),
            outcome_id_two: (0.2, 0.0, 0.04),
            outcome_id_three: (0.6, 1.0, 0.16),
        },
    )

    assert summary.dimension == "source"
    assert summary.advisory_only is True
    assert summary.eligible_rows == 1
    assert summary.sparse_rows == 1
    assert summary.rows[0].label == "Reuters"
    assert summary.rows[0].sample_size == 2
    assert summary.rows[0].mean_predicted_probability == pytest.approx(0.5)
    assert summary.rows[0].observed_rate == pytest.approx(0.5)
    assert summary.rows[0].mean_brier_score == pytest.approx(0.04)
    assert summary.rows[0].calibration_gap == pytest.approx(0.0)
    assert summary.rows[0].eligible is True


def test_build_reliability_summary_applies_sparse_guardrails() -> None:
    service = CalibrationDashboardService(session=AsyncMock())
    outcome_id_one = uuid4()
    outcome_id_two = uuid4()

    summary = service._build_reliability_summary_from_pairs(
        dimension="source_tier",
        min_sample_size=3,
        pairs=[
            ("wire", "wire", outcome_id_one),
            ("wire", "wire", outcome_id_one),
            ("wire", "wire", outcome_id_two),
        ],
        outcome_metrics={
            outcome_id_one: (0.7, 1.0, 0.09),
            outcome_id_two: (0.4, 0.0, 0.16),
        },
    )

    assert summary.eligible_rows == 0
    assert summary.sparse_rows == 1
    assert summary.rows[0].sample_size == 2
    assert summary.rows[0].eligible is False
    assert summary.rows[0].confidence == "insufficient"
    assert "Sparse sample" in summary.rows[0].advisory_note


@pytest.mark.asyncio
async def test_emit_drift_notifications_forwards_to_webhook_notifier() -> None:
    notifier = AsyncMock()
    service = CalibrationDashboardService(
        session=AsyncMock(),
        drift_alert_notifier=notifier,
    )
    generated_at = datetime(2026, 2, 9, tzinfo=UTC)
    alerts = [
        CalibrationDriftAlert(
            alert_type="mean_brier_drift",
            severity="warning",
            metric_name="mean_brier_score",
            metric_value=0.22,
            threshold=0.2,
            sample_size=12,
            message="Threshold exceeded.",
        )
    ]

    await service._emit_drift_notifications(
        trend_id=None,
        drift_alerts=alerts,
        generated_at=generated_at,
    )

    notifier.notify.assert_awaited_once()
