from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.report_generator import ReportGenerator

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_load_contradiction_analytics_summarizes_resolution(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    now = datetime.now(tz=UTC)
    event_id_one = uuid4()
    event_id_two = uuid4()

    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                SimpleNamespace(
                    event_id=event_id_one,
                    first_contradiction_at=now - timedelta(hours=8),
                ),
                SimpleNamespace(
                    event_id=event_id_two,
                    first_contradiction_at=now - timedelta(hours=5),
                ),
            ]
        ),
        SimpleNamespace(
            all=lambda: [
                SimpleNamespace(
                    target_id=event_id_one,
                    action="invalidate",
                    created_at=now - timedelta(hours=2),
                ),
                SimpleNamespace(
                    target_id=event_id_one,
                    action="pin",
                    created_at=now - timedelta(hours=1),
                ),
                SimpleNamespace(
                    target_id=event_id_two,
                    action="mark_noise",
                    created_at=now - timedelta(hours=4),
                ),
            ]
        ),
    ]

    result = await generator._load_contradiction_analytics(
        trend_id=uuid4(),
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    assert result["contradicted_events_count"] == 2
    assert result["resolved_events_count"] == 2
    assert result["unresolved_events_count"] == 0
    assert result["resolution_rate"] == 1.0
    assert result["avg_resolution_time_hours"] == 3.5
    assert result["resolution_actions"] == {
        "invalidate": 1,
        "mark_noise": 1,
    }


@pytest.mark.asyncio
async def test_load_contradiction_analytics_handles_empty_period(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    now = datetime.now(tz=UTC)
    mock_db_session.execute.return_value = SimpleNamespace(all=list)

    result = await generator._load_contradiction_analytics(
        trend_id=uuid4(),
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    assert result == {
        "contradicted_events_count": 0,
        "resolved_events_count": 0,
        "unresolved_events_count": 0,
        "resolution_rate": 0.0,
        "avg_resolution_time_hours": None,
        "resolution_actions": {},
    }
    assert mock_db_session.execute.await_count == 1


@pytest.mark.asyncio
async def test_build_weekly_statistics_includes_contradiction_analytics(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.55,
        get_probability_at=AsyncMock(return_value=0.50),
        get_direction=AsyncMock(return_value="rising"),
    )
    mock_db_session.scalar.return_value = 7
    analytics = {
        "contradicted_events_count": 3,
        "resolved_events_count": 1,
        "unresolved_events_count": 2,
        "resolution_rate": 0.333333,
        "avg_resolution_time_hours": 11.25,
        "resolution_actions": {"invalidate": 1},
    }
    generator._load_contradiction_analytics = AsyncMock(return_value=analytics)

    now = datetime.now(tz=UTC)
    result = await generator._build_weekly_statistics(
        trend=trend,
        trend_engine=trend_engine,
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    assert result["current_probability"] == 0.55
    assert result["weekly_change"] == 0.05
    assert result["direction"] == "rising"
    assert result["evidence_count_weekly"] == 7
    assert result["contradiction_analytics"] == analytics


@pytest.mark.asyncio
async def test_build_monthly_statistics_includes_contradiction_analytics(mock_db_session) -> None:
    generator = ReportGenerator(session=mock_db_session, client=None)
    trend = SimpleNamespace(id=uuid4())
    trend_engine = SimpleNamespace(
        get_probability=lambda _trend: 0.42,
        get_probability_at=AsyncMock(return_value=0.40),
        get_direction=AsyncMock(return_value="stable"),
    )
    mock_db_session.scalar.return_value = 11
    generator._calculate_previous_period_change = AsyncMock(return_value=0.03)
    generator._load_category_breakdown = AsyncMock(return_value={"military": 4})
    generator._load_source_breakdown = AsyncMock(return_value={"rss": 6})
    generator._load_weekly_reports = AsyncMock(return_value=[])
    analytics = {
        "contradicted_events_count": 4,
        "resolved_events_count": 3,
        "unresolved_events_count": 1,
        "resolution_rate": 0.75,
        "avg_resolution_time_hours": 8.5,
        "resolution_actions": {"mark_noise": 2, "invalidate": 1},
    }
    generator._load_contradiction_analytics = AsyncMock(return_value=analytics)

    now = datetime.now(tz=UTC)
    result = await generator._build_monthly_statistics(
        trend=trend,
        trend_engine=trend_engine,
        period_start=now - timedelta(days=30),
        period_end=now,
    )

    assert result["current_probability"] == 0.42
    assert result["monthly_change"] == 0.02
    assert result["change_vs_previous_month"] == -0.01
    assert result["direction"] == "stable"
    assert result["evidence_count_monthly"] == 11
    assert result["contradiction_analytics"] == analytics


def test_fallback_narrative_weekly_includes_confidence_and_contradictions() -> None:
    trend = SimpleNamespace(name="Signal Watch")
    narrative = ReportGenerator._fallback_narrative(
        trend=trend,
        report_type="weekly",
        statistics={
            "current_probability": 0.42,
            "weekly_change": 0.05,
            "direction": "rising",
            "evidence_count_weekly": 4,
            "contradiction_analytics": {
                "contradicted_events_count": 3,
                "resolved_events_count": 1,
                "unresolved_events_count": 2,
            },
        },
    )

    assert "Signal Watch is currently at 42.0%" in narrative
    assert "Confidence is limited" in narrative
    assert "3 events (1 resolved, 2 unresolved)" in narrative


def test_fallback_narrative_monthly_scales_confidence_with_coverage() -> None:
    trend = SimpleNamespace(name="Signal Watch")
    narrative = ReportGenerator._fallback_narrative(
        trend=trend,
        report_type="monthly",
        statistics={
            "current_probability": 0.58,
            "monthly_change": -0.02,
            "direction": "stable",
            "evidence_count_monthly": 24,
        },
    )

    assert "monthly change of -2.0%" in narrative
    assert "Confidence is high" in narrative
