"""Coverage-health report endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.source_coverage import (
    CoverageCounts,
    CoverageHealthReport,
    build_source_coverage_report,
    deserialize_coverage_report,
    load_latest_coverage_snapshot,
)
from src.storage.database import get_session

router = APIRouter()


class CoverageCountsResponse(BaseModel):
    """Coverage counts for one slice."""

    seen: int
    processable: int
    processed: int
    deferred: int
    skipped_by_language: int
    pending_processable: int
    processing: int
    classified: int
    noise: int
    error: int


class CoverageSegmentResponse(BaseModel):
    """Coverage row for one dimension key."""

    key: str
    label: str
    counts: CoverageCountsResponse
    processed_ratio: float
    pending_ratio: float
    change_ratio: float | None


class CoverageDimensionResponse(BaseModel):
    """Coverage rows for a dimension."""

    dimension: str
    multi_value: bool
    rows: list[CoverageSegmentResponse]


class CoverageAlertResponse(BaseModel):
    """Coverage drop alert."""

    severity: str
    dimension: str
    key: str
    label: str
    current_seen: int
    previous_seen: int
    change_ratio: float
    message: str


class CoverageHealthResponse(BaseModel):
    """Recent source coverage-health payload."""

    generated_at: datetime
    window_start: datetime
    window_end: datetime
    lookback_hours: int
    report_source: str
    snapshot_id: UUID | None
    artifact_path: str | None
    total: CoverageCountsResponse
    dimensions: list[CoverageDimensionResponse]
    alerts: list[CoverageAlertResponse]


def _to_coverage_response(
    *,
    report: CoverageHealthReport,
    report_source: str,
) -> CoverageHealthResponse:
    def counts_response(counts: CoverageCounts) -> CoverageCountsResponse:
        return CoverageCountsResponse(
            seen=counts.seen,
            processable=counts.processable,
            processed=counts.processed,
            deferred=counts.deferred,
            skipped_by_language=counts.skipped_by_language,
            pending_processable=counts.pending_processable,
            processing=counts.processing,
            classified=counts.classified,
            noise=counts.noise,
            error=counts.error,
        )

    return CoverageHealthResponse(
        generated_at=report.generated_at,
        window_start=report.window_start,
        window_end=report.window_end,
        lookback_hours=report.lookback_hours,
        report_source=report_source,
        snapshot_id=report.snapshot_id,
        artifact_path=report.artifact_path,
        total=counts_response(report.total),
        dimensions=[
            CoverageDimensionResponse(
                dimension=summary.dimension,
                multi_value=summary.multi_value,
                rows=[
                    CoverageSegmentResponse(
                        key=row.key,
                        label=row.label,
                        counts=counts_response(row.counts),
                        processed_ratio=row.processed_ratio,
                        pending_ratio=row.pending_ratio,
                        change_ratio=row.change_ratio,
                    )
                    for row in summary.rows
                ],
            )
            for summary in report.dimensions
        ],
        alerts=[
            CoverageAlertResponse(
                severity=alert.severity,
                dimension=alert.dimension,
                key=alert.key,
                label=alert.label,
                current_seen=alert.current_seen,
                previous_seen=alert.previous_seen,
                change_ratio=alert.change_ratio,
                message=alert.message,
            )
            for alert in report.alerts
        ],
    )


@router.get("/coverage", response_model=CoverageHealthResponse)
async def get_coverage_health(
    prefer_live: Annotated[bool, Query()] = False,
    session: AsyncSession = Depends(get_session),
) -> CoverageHealthResponse:
    """Get recent source coverage health distinct from source freshness."""
    latest_snapshot = None if prefer_live else await load_latest_coverage_snapshot(session)
    if latest_snapshot is not None:
        return _to_coverage_response(
            report=deserialize_coverage_report(latest_snapshot.payload),
            report_source="snapshot",
        )

    if prefer_live:
        latest_snapshot = await load_latest_coverage_snapshot(session)
    previous_payload = latest_snapshot.payload if latest_snapshot is not None else None
    report = await build_source_coverage_report(
        session=session,
        previous_snapshot_payload=previous_payload,
    )
    return _to_coverage_response(report=report, report_source="live")
