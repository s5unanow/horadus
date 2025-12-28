"""
Reports API endpoints.

Endpoints for accessing generated intelligence reports.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_session

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class ReportSummary(BaseModel):
    """Brief report summary for listings."""

    id: UUID
    report_type: str
    period_start: datetime
    period_end: datetime
    trend_name: str | None
    created_at: datetime


class ReportResponse(BaseModel):
    """Full report response."""

    id: UUID
    report_type: str
    period_start: datetime
    period_end: datetime
    trend_id: UUID | None
    trend_name: str | None
    statistics: dict
    narrative: str | None
    top_events: list[dict] | None
    created_at: datetime


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
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ReportResponse:
    """
    Get a specific report.
    """
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


@router.get("/latest/weekly", response_model=ReportResponse)
async def get_latest_weekly(
    trend_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> ReportResponse:
    """
    Get the most recent weekly report.

    Optionally filter by trend.
    """
    # TODO: Implement
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )
