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
