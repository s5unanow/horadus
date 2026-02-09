"""
Reports API endpoints.

Endpoints for accessing generated intelligence reports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.calibration_dashboard import CalibrationDashboardService
from src.storage.database import get_session
from src.storage.models import Report, Trend

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class ReportSummary(BaseModel):
    """Brief report summary for listings."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "9a4f5a7c-9d0d-4b4a-a777-3aa64be6a02c",
                "report_type": "weekly",
                "period_start": "2026-02-01T00:00:00Z",
                "period_end": "2026-02-08T00:00:00Z",
                "trend_name": "EU-Russia Military Conflict",
                "created_at": "2026-02-08T00:01:00Z",
            }
        }
    )

    id: UUID
    report_type: str
    period_start: datetime
    period_end: datetime
    trend_name: str | None
    created_at: datetime


class ReportResponse(BaseModel):
    """Full report response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "9a4f5a7c-9d0d-4b4a-a777-3aa64be6a02c",
                "report_type": "monthly",
                "period_start": "2026-01-08T00:00:00Z",
                "period_end": "2026-02-07T00:00:00Z",
                "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "trend_name": "EU-Russia Military Conflict",
                "statistics": {
                    "current_probability": 0.18,
                    "monthly_change": 0.04,
                    "direction": "rising",
                },
                "narrative": "Probability rose this month due to repeated corroborated signals.",
                "top_events": [
                    {
                        "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                        "impact_score": 0.12,
                    }
                ],
                "created_at": "2026-02-08T00:01:00Z",
            }
        }
    )

    id: UUID
    report_type: str
    period_start: datetime
    period_end: datetime
    trend_id: UUID | None
    trend_name: str | None
    statistics: dict[str, Any]
    narrative: str | None
    top_events: list[dict[str, Any]] | None
    created_at: datetime


class CalibrationCurveBucketResponse(BaseModel):
    """Calibration curve bucket from dashboard report."""

    bucket_start: float
    bucket_end: float
    prediction_count: int
    actual_rate: float
    expected_rate: float
    calibration_error: float


class BrierScoreTimeseriesResponse(BaseModel):
    """Brier score timeline point."""

    period_start: datetime
    period_end: datetime
    mean_brier_score: float
    sample_size: int


class TrendMovementResponse(BaseModel):
    """Trend movement visibility row."""

    trend_id: UUID
    trend_name: str
    current_probability: float
    weekly_change: float
    risk_level: str
    top_movers_7d: list[str]
    movement_chart: str


class CalibrationDriftAlertResponse(BaseModel):
    """Calibration drift alert summary."""

    alert_type: str
    severity: str
    metric_name: str
    metric_value: float
    threshold: float
    sample_size: int
    message: str


class TrendCoverageResponse(BaseModel):
    """Per-trend calibration coverage summary row."""

    trend_id: UUID
    trend_name: str
    total_predictions: int
    resolved_predictions: int
    resolved_ratio: float


class CalibrationCoverageResponse(BaseModel):
    """Calibration coverage guardrail summary."""

    min_resolved_per_trend: int
    min_resolved_ratio: float
    total_predictions: int
    resolved_predictions: int
    unresolved_predictions: int
    overall_resolved_ratio: float
    trends_with_predictions: int
    trends_meeting_min: int
    trends_below_min: int
    low_sample_trends: list[TrendCoverageResponse]
    coverage_sufficient: bool


class CalibrationDashboardResponse(BaseModel):
    """Cross-trend calibration dashboard payload."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "generated_at": "2026-02-08T12:00:00Z",
                "period_start": "2025-11-10T00:00:00Z",
                "period_end": "2026-02-08T12:00:00Z",
                "total_predictions": 42,
                "resolved_predictions": 38,
                "mean_brier_score": 0.191,
                "calibration_curve": [
                    {
                        "bucket_start": 0.2,
                        "bucket_end": 0.3,
                        "prediction_count": 10,
                        "actual_rate": 0.3,
                        "expected_rate": 0.25,
                        "calibration_error": 0.05,
                    }
                ],
                "brier_score_over_time": [
                    {
                        "period_start": "2026-01-05T00:00:00Z",
                        "period_end": "2026-01-12T00:00:00Z",
                        "mean_brier_score": 0.176,
                        "sample_size": 5,
                    }
                ],
                "reliability_notes": [
                    "When we predicted 20%-30%, it happened 30% of the time (n=10)."
                ],
                "trend_movements": [
                    {
                        "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                        "trend_name": "EU-Russia Military Conflict",
                        "current_probability": 0.183,
                        "weekly_change": 0.021,
                        "risk_level": "guarded",
                        "top_movers_7d": ["military_movement", "diplomatic_breakdown"],
                        "movement_chart": "._-~=+*#%@",
                    }
                ],
                "drift_alerts": [
                    {
                        "alert_type": "mean_brier_drift",
                        "severity": "warning",
                        "metric_name": "mean_brier_score",
                        "metric_value": 0.214,
                        "threshold": 0.2,
                        "sample_size": 38,
                        "message": "Mean Brier score exceeded calibration drift threshold (0.214 >= 0.200).",
                    }
                ],
                "coverage": {
                    "min_resolved_per_trend": 5,
                    "min_resolved_ratio": 0.5,
                    "total_predictions": 42,
                    "resolved_predictions": 38,
                    "unresolved_predictions": 4,
                    "overall_resolved_ratio": 0.904762,
                    "trends_with_predictions": 3,
                    "trends_meeting_min": 2,
                    "trends_below_min": 1,
                    "low_sample_trends": [
                        {
                            "trend_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                            "trend_name": "EU-Russia Military Conflict",
                            "total_predictions": 4,
                            "resolved_predictions": 2,
                            "resolved_ratio": 0.5,
                        }
                    ],
                    "coverage_sufficient": False,
                },
            }
        }
    )

    generated_at: datetime
    period_start: datetime
    period_end: datetime
    total_predictions: int
    resolved_predictions: int
    mean_brier_score: float | None
    calibration_curve: list[CalibrationCurveBucketResponse]
    brier_score_over_time: list[BrierScoreTimeseriesResponse]
    reliability_notes: list[str]
    trend_movements: list[TrendMovementResponse]
    drift_alerts: list[CalibrationDriftAlertResponse]
    coverage: CalibrationCoverageResponse


def _normalize_top_events(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        nested = value.get("events")
        if isinstance(nested, list):
            return [row for row in nested if isinstance(row, dict)]
    return None


def _to_report_response(report: Report, trend_name: str | None) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        report_type=report.report_type,
        period_start=report.period_start,
        period_end=report.period_end,
        trend_id=report.trend_id,
        trend_name=trend_name,
        statistics=report.statistics,
        narrative=report.narrative,
        top_events=_normalize_top_events(report.top_events),
        created_at=report.created_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[ReportSummary])
async def list_reports(
    report_type: str | None = None,
    trend_id: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[ReportSummary]:
    """
    List available reports.

    Can filter by type (weekly, monthly, retrospective) or trend.
    """
    query = (
        select(Report, Trend.name)
        .outerjoin(Trend, Trend.id == Report.trend_id)
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    if report_type is not None:
        query = query.where(Report.report_type == report_type)
    if trend_id is not None:
        query = query.where(Report.trend_id == trend_id)

    rows = (await session.execute(query)).all()
    return [
        ReportSummary(
            id=report.id,
            report_type=report.report_type,
            period_start=report.period_start,
            period_end=report.period_end,
            trend_name=trend_name,
            created_at=report.created_at,
        )
        for report, trend_name in rows
    ]


@router.get("/calibration", response_model=CalibrationDashboardResponse)
async def get_calibration_dashboard(
    trend_id: UUID | None = None,
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> CalibrationDashboardResponse:
    """
    Get cross-trend calibration dashboard and movement visibility.
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be less than or equal to end_date",
        )

    service = CalibrationDashboardService(session)
    dashboard = await service.build_dashboard(
        trend_id=trend_id,
        start_date=start_date,
        end_date=end_date,
    )
    return CalibrationDashboardResponse(
        generated_at=dashboard.generated_at,
        period_start=dashboard.period_start,
        period_end=dashboard.period_end,
        total_predictions=dashboard.total_predictions,
        resolved_predictions=dashboard.resolved_predictions,
        mean_brier_score=dashboard.mean_brier_score,
        calibration_curve=[
            CalibrationCurveBucketResponse(
                bucket_start=bucket.bucket_start,
                bucket_end=bucket.bucket_end,
                prediction_count=bucket.prediction_count,
                actual_rate=bucket.actual_rate,
                expected_rate=bucket.expected_rate,
                calibration_error=bucket.calibration_error,
            )
            for bucket in dashboard.calibration_curve
        ],
        brier_score_over_time=[
            BrierScoreTimeseriesResponse(
                period_start=point.period_start,
                period_end=point.period_end,
                mean_brier_score=point.mean_brier_score,
                sample_size=point.sample_size,
            )
            for point in dashboard.brier_score_over_time
        ],
        reliability_notes=dashboard.reliability_notes,
        trend_movements=[
            TrendMovementResponse(
                trend_id=row.trend_id,
                trend_name=row.trend_name,
                current_probability=row.current_probability,
                weekly_change=row.weekly_change,
                risk_level=row.risk_level,
                top_movers_7d=row.top_movers_7d,
                movement_chart=row.movement_chart,
            )
            for row in dashboard.trend_movements
        ],
        drift_alerts=[
            CalibrationDriftAlertResponse(
                alert_type=alert.alert_type,
                severity=alert.severity,
                metric_name=alert.metric_name,
                metric_value=alert.metric_value,
                threshold=alert.threshold,
                sample_size=alert.sample_size,
                message=alert.message,
            )
            for alert in dashboard.drift_alerts
        ],
        coverage=CalibrationCoverageResponse(
            min_resolved_per_trend=dashboard.coverage.min_resolved_per_trend,
            min_resolved_ratio=dashboard.coverage.min_resolved_ratio,
            total_predictions=dashboard.coverage.total_predictions,
            resolved_predictions=dashboard.coverage.resolved_predictions,
            unresolved_predictions=dashboard.coverage.unresolved_predictions,
            overall_resolved_ratio=dashboard.coverage.overall_resolved_ratio,
            trends_with_predictions=dashboard.coverage.trends_with_predictions,
            trends_meeting_min=dashboard.coverage.trends_meeting_min,
            trends_below_min=dashboard.coverage.trends_below_min,
            low_sample_trends=[
                TrendCoverageResponse(
                    trend_id=row.trend_id,
                    trend_name=row.trend_name,
                    total_predictions=row.total_predictions,
                    resolved_predictions=row.resolved_predictions,
                    resolved_ratio=row.resolved_ratio,
                )
                for row in dashboard.coverage.low_sample_trends
            ],
            coverage_sufficient=dashboard.coverage.coverage_sufficient,
        ),
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ReportResponse:
    """
    Get a specific report.
    """
    row = (
        await session.execute(
            select(Report, Trend.name)
            .outerjoin(Trend, Trend.id == Report.trend_id)
            .where(Report.id == report_id)
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found",
        )

    report, trend_name = row
    return _to_report_response(report, trend_name)


@router.get("/latest/weekly", response_model=ReportResponse)
async def get_latest_weekly(
    trend_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> ReportResponse:
    """
    Get the most recent weekly report.

    Optionally filter by trend.
    """
    query = (
        select(Report, Trend.name)
        .outerjoin(Trend, Trend.id == Report.trend_id)
        .where(Report.report_type == "weekly")
        .order_by(Report.period_end.desc(), Report.created_at.desc())
        .limit(1)
    )
    if trend_id is not None:
        query = query.where(Report.trend_id == trend_id)

    row = (await session.execute(query)).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly reports found",
        )

    report, trend_name = row
    return _to_report_response(report, trend_name)


@router.get("/latest/monthly", response_model=ReportResponse)
async def get_latest_monthly(
    trend_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> ReportResponse:
    """
    Get the most recent monthly report.

    Optionally filter by trend.
    """
    query = (
        select(Report, Trend.name)
        .outerjoin(Trend, Trend.id == Report.trend_id)
        .where(Report.report_type == "monthly")
        .order_by(Report.period_end.desc(), Report.created_at.desc())
        .limit(1)
    )
    if trend_id is not None:
        query = query.where(Report.trend_id == trend_id)

    row = (await session.execute(query)).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No monthly reports found",
        )

    report, trend_name = row
    return _to_report_response(report, trend_name)
