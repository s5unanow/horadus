from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.calibration_dashboard import (
    BrierTimeseriesPoint,
    CalibrationBucketSummary,
    CalibrationCoverageSummary,
    CalibrationDashboardReport,
    CalibrationDriftAlert,
    TrendMovement,
)
from src.core.dashboard_export import (
    build_calibration_dashboard_payload,
    export_calibration_dashboard,
)

pytestmark = pytest.mark.unit


def _build_dashboard_report() -> CalibrationDashboardReport:
    now = datetime.now(tz=UTC)
    return CalibrationDashboardReport(
        generated_at=now,
        period_start=now - timedelta(days=30),
        period_end=now,
        total_predictions=15,
        resolved_predictions=12,
        mean_brier_score=0.21,
        calibration_curve=[
            CalibrationBucketSummary(
                bucket_start=0.2,
                bucket_end=0.3,
                prediction_count=8,
                actual_rate=0.4,
                expected_rate=0.25,
                calibration_error=0.15,
            )
        ],
        brier_score_over_time=[
            BrierTimeseriesPoint(
                period_start=now - timedelta(days=7),
                period_end=now,
                mean_brier_score=0.2,
                sample_size=5,
            )
        ],
        reliability_notes=["When we predicted 20%-30%, it happened 40% of the time (n=8)."],
        trend_movements=[
            TrendMovement(
                trend_id=uuid4(),
                trend_name="EU-Russia",
                current_probability=0.31,
                weekly_change=0.03,
                risk_level="elevated",
                top_movers_7d=["military_movement"],
                movement_chart="._-=+*",
            ),
            TrendMovement(
                trend_id=uuid4(),
                trend_name="US-China",
                current_probability=0.22,
                weekly_change=-0.01,
                risk_level="guarded",
                top_movers_7d=["trade_restrictions"],
                movement_chart="._--~~",
            ),
        ],
        drift_alerts=[
            CalibrationDriftAlert(
                alert_type="mean_brier_drift",
                severity="warning",
                metric_name="mean_brier_score",
                metric_value=0.21,
                threshold=0.2,
                sample_size=12,
                message="Mean Brier score exceeded calibration drift threshold (0.210 >= 0.200).",
            )
        ],
        coverage=CalibrationCoverageSummary(
            min_resolved_per_trend=5,
            min_resolved_ratio=0.5,
            total_predictions=15,
            resolved_predictions=12,
            unresolved_predictions=3,
            overall_resolved_ratio=0.8,
            trends_with_predictions=2,
            trends_meeting_min=2,
            trends_below_min=0,
            low_sample_trends=[],
            coverage_sufficient=True,
        ),
    )


def test_build_payload_serializes_datetimes_and_limits_rows() -> None:
    payload = build_calibration_dashboard_payload(_build_dashboard_report(), trend_limit=1)

    assert payload["generated_at"].endswith("Z")
    assert payload["period_start"].endswith("Z")
    assert payload["period_end"].endswith("Z")
    assert len(payload["trend_movements"]) == 1
    assert payload["drift_alerts"][0]["alert_type"] == "mean_brier_drift"


def test_export_dashboard_writes_timestamped_and_latest_files(tmp_path: Path) -> None:
    result = export_calibration_dashboard(
        _build_dashboard_report(),
        output_dir=tmp_path,
        trend_limit=2,
    )

    assert result.json_path.exists()
    assert result.html_path.exists()
    assert result.latest_json_path.exists()
    assert result.latest_html_path.exists()
    assert result.index_html_path.exists()

    exported_payload = json.loads(result.latest_json_path.read_text(encoding="utf-8"))
    assert exported_payload["resolved_predictions"] == 12
    assert len(exported_payload["trend_movements"]) == 2
