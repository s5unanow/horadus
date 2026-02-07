from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.reports import get_latest_monthly, get_latest_weekly, get_report, list_reports
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
        top_events={"events": [{"event_id": str(uuid4()), "impact_score": 0.12}]},
        created_at=now,
    )


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
