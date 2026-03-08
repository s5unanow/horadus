from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.reports import (
    _normalize_top_events,
    get_calibration_dashboard,
    get_latest_monthly,
    get_latest_weekly,
    get_report,
    list_reports,
)
from src.core.calibration_dashboard import (
    BrierTimeseriesPoint,
    CalibrationBucketSummary,
    CalibrationCoverageSummary,
    CalibrationDashboardReport,
    CalibrationDriftAlert,
    TrendCoverageSummary,
    TrendMovement,
)
from src.storage.models import Report

pytestmark = pytest.mark.unit


def _build_report(*, trend_id: object | None = None, report_type: str = "weekly") -> Report:
    now = datetime.now(tz=UTC)
    return Report(
        id=uuid4(),
        report_type=report_type,
        period_start=now - timedelta(days=7),
        period_end=now,
        trend_id=trend_id,
        statistics={
            "current_probability": 0.24,
            "weekly_change": 0.03,
            "direction": "rising",
            "evidence_count_weekly": 5,
        },
        narrative="Trend rose this week due to repeated corroborated signals.",
        grounding_status="grounded",
        grounding_violation_count=0,
        grounding_references=None,
        top_events={"events": [{"event_id": str(uuid4()), "impact_score": 0.12}]},
        created_at=now,
    )


def test_normalize_top_events_accepts_lists_and_rejects_invalid_shapes() -> None:
    event_id = str(uuid4())

    assert _normalize_top_events([{"event_id": event_id}, "skip"]) == [{"event_id": event_id}]
    assert _normalize_top_events({"events": "not-a-list"}) is None
    assert _normalize_top_events("invalid") is None


@pytest.mark.asyncio
async def test_list_reports_returns_summaries(mock_db_session) -> None:
    trend_id = uuid4()
    report = _build_report(trend_id=trend_id)
    mock_db_session.execute.return_value = SimpleNamespace(all=lambda: [(report, "EU-Russia")])

    result = await list_reports(
        report_type="weekly",
        trend_id=trend_id,
        limit=20,
        session=mock_db_session,
    )

    assert len(result) == 1
    assert result[0].id == report.id
    assert result[0].report_type == "weekly"
    assert result[0].trend_name == "EU-Russia"


@pytest.mark.asyncio
async def test_list_reports_supports_individual_filters(mock_db_session) -> None:
    trend_id = uuid4()
    report = _build_report(trend_id=trend_id)

    mock_db_session.execute.return_value = SimpleNamespace(all=lambda: [(report, "EU-Russia")])
    by_type = await list_reports(
        report_type="weekly",
        trend_id=None,
        limit=10,
        session=mock_db_session,
    )
    by_type_query = str(mock_db_session.execute.await_args.args[0])

    mock_db_session.execute.return_value = SimpleNamespace(all=lambda: [(report, "EU-Russia")])
    by_trend = await list_reports(
        report_type=None,
        trend_id=trend_id,
        limit=10,
        session=mock_db_session,
    )
    by_trend_query = str(mock_db_session.execute.await_args.args[0])

    assert by_type[0].id == report.id
    assert "reports.report_type" in by_type_query
    assert by_trend[0].id == report.id
    assert "reports.trend_id" in by_trend_query


@pytest.mark.asyncio
async def test_get_report_returns_404_when_missing(mock_db_session) -> None:
    report_id = uuid4()
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: None)

    with pytest.raises(HTTPException, match="not found") as exc:
        await get_report(report_id=report_id, session=mock_db_session)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_report_returns_report_payload(mock_db_session) -> None:
    trend_id = uuid4()
    report = _build_report(trend_id=trend_id)
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: (report, "EU-Russia"))

    result = await get_report(report_id=report.id, session=mock_db_session)

    assert result.id == report.id
    assert result.trend_id == trend_id
    assert result.trend_name == "EU-Russia"
    assert result.grounding_status == "grounded"
    assert result.grounding_violation_count == 0
    assert result.top_events is not None
    assert len(result.top_events) == 1


@pytest.mark.asyncio
async def test_get_latest_weekly_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: None)

    with pytest.raises(HTTPException, match="No weekly reports found") as exc:
        await get_latest_weekly(session=mock_db_session)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_weekly_returns_report(mock_db_session) -> None:
    report = _build_report(trend_id=uuid4(), report_type="weekly")
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: (report, "EU-Russia"))

    result = await get_latest_weekly(session=mock_db_session)

    assert result.id == report.id
    assert result.report_type == "weekly"
    assert result.trend_name == "EU-Russia"


@pytest.mark.asyncio
async def test_get_latest_weekly_filters_by_trend(mock_db_session) -> None:
    trend_id = uuid4()
    report = _build_report(trend_id=trend_id, report_type="weekly")
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: (report, "EU-Russia"))

    result = await get_latest_weekly(trend_id=trend_id, session=mock_db_session)

    assert result.id == report.id
    query_text = str(mock_db_session.execute.await_args.args[0])
    assert "reports.trend_id" in query_text


@pytest.mark.asyncio
async def test_get_latest_monthly_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: None)

    with pytest.raises(HTTPException, match="No monthly reports found") as exc:
        await get_latest_monthly(session=mock_db_session)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_latest_monthly_returns_report(mock_db_session) -> None:
    report = _build_report(trend_id=uuid4(), report_type="monthly")
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: (report, "EU-Russia"))

    result = await get_latest_monthly(session=mock_db_session)

    assert result.id == report.id
    assert result.report_type == "monthly"
    assert result.trend_name == "EU-Russia"


@pytest.mark.asyncio
async def test_get_latest_monthly_filters_by_trend(mock_db_session) -> None:
    trend_id = uuid4()
    report = _build_report(trend_id=trend_id, report_type="monthly")
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: (report, "EU-Russia"))

    result = await get_latest_monthly(trend_id=trend_id, session=mock_db_session)

    assert result.id == report.id
    query_text = str(mock_db_session.execute.await_args.args[0])
    assert "reports.trend_id" in query_text


@pytest.mark.asyncio
async def test_get_calibration_dashboard_returns_payload(mock_db_session, monkeypatch) -> None:
    now = datetime.now(tz=UTC)
    trend_id = uuid4()
    dashboard = CalibrationDashboardReport(
        generated_at=now,
        period_start=now - timedelta(days=30),
        period_end=now,
        total_predictions=12,
        resolved_predictions=10,
        mean_brier_score=0.19,
        calibration_curve=[
            CalibrationBucketSummary(
                bucket_start=0.2,
                bucket_end=0.3,
                prediction_count=5,
                actual_rate=0.4,
                expected_rate=0.25,
                calibration_error=0.15,
            )
        ],
        brier_score_over_time=[
            BrierTimeseriesPoint(
                period_start=now - timedelta(days=7),
                period_end=now,
                mean_brier_score=0.18,
                sample_size=5,
            )
        ],
        reliability_notes=["When we predicted 20%-30%, it happened 40% of the time (n=5)."],
        trend_movements=[
            TrendMovement(
                trend_id=trend_id,
                trend_name="EU-Russia",
                current_probability=0.31,
                weekly_change=0.04,
                risk_level="elevated",
                top_movers_7d=["military_movement"],
                movement_chart="._-=+*",
            )
        ],
        drift_alerts=[
            CalibrationDriftAlert(
                alert_type="mean_brier_drift",
                severity="warning",
                metric_name="mean_brier_score",
                metric_value=0.19,
                threshold=0.2,
                sample_size=10,
                message="Mean Brier score approaching drift threshold.",
            )
        ],
        coverage=CalibrationCoverageSummary(
            min_resolved_per_trend=5,
            min_resolved_ratio=0.5,
            total_predictions=12,
            resolved_predictions=10,
            unresolved_predictions=2,
            overall_resolved_ratio=0.833333,
            trends_with_predictions=1,
            trends_meeting_min=1,
            trends_below_min=0,
            low_sample_trends=[
                TrendCoverageSummary(
                    trend_id=trend_id,
                    trend_name="EU-Russia",
                    total_predictions=12,
                    resolved_predictions=10,
                    resolved_ratio=0.833333,
                )
            ],
            coverage_sufficient=True,
        ),
    )

    class _Service:
        def __init__(self, session) -> None:
            assert session is mock_db_session

        async def build_dashboard(
            self,
            *,
            trend_id,
            start_date,
            end_date,
        ) -> CalibrationDashboardReport:
            assert trend_id is None
            assert start_date is None
            assert end_date is None
            return dashboard

    monkeypatch.setattr("src.api.routes.reports.CalibrationDashboardService", _Service)

    result = await get_calibration_dashboard(
        trend_id=None,
        start_date=None,
        end_date=None,
        session=mock_db_session,
    )

    assert result.total_predictions == 12
    assert result.resolved_predictions == 10
    assert result.mean_brier_score == pytest.approx(0.19)
    assert result.calibration_curve[0].actual_rate == pytest.approx(0.4)
    assert result.trend_movements[0].trend_name == "EU-Russia"
    assert result.trend_movements[0].movement_chart == "._-=+*"
    assert len(result.drift_alerts) == 1
    assert result.drift_alerts[0].alert_type == "mean_brier_drift"
    assert result.coverage.coverage_sufficient is True
    assert result.source_reliability.dimension == "source"
    assert result.source_tier_reliability.dimension == "source_tier"


@pytest.mark.asyncio
async def test_get_calibration_dashboard_rejects_invalid_date_range(mock_db_session) -> None:
    now = datetime.now(tz=UTC)

    with pytest.raises(
        HTTPException, match="start_date must be less than or equal to end_date"
    ) as exc:
        await get_calibration_dashboard(
            trend_id=None,
            start_date=now,
            end_date=now - timedelta(days=1),
            session=mock_db_session,
        )

    assert exc.value.status_code == 400
