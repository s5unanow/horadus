from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.source_freshness import (
    _as_utc,
    _collector_interval_minutes,
    build_source_freshness_report,
)
from src.storage.models import Source, SourceType

pytestmark = pytest.mark.unit


def _build_source(
    *,
    name: str,
    source_type: SourceType,
    last_fetched_at: datetime | None,
) -> Source:
    return Source(
        id=uuid4(),
        type=source_type,
        name=name,
        url="https://example.com/feed.xml",
        credibility_score=0.8,
        source_tier="regional",
        reporting_type="secondary",
        config={},
        is_active=True,
        last_fetched_at=last_fetched_at,
        error_count=0,
    )


def test_as_utc_normalizes_naive_and_aware_datetimes() -> None:
    naive = datetime(2026, 2, 16, 12, 0, tzinfo=UTC).replace(tzinfo=None)
    aware = datetime(2026, 2, 16, 14, 0, tzinfo=UTC)

    assert _as_utc(naive).tzinfo is UTC
    assert _as_utc(naive).hour == 12
    assert _as_utc(aware).tzinfo is UTC
    assert _as_utc(aware).hour == 14


def test_collector_interval_minutes_handles_supported_and_unknown_collectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.core.source_freshness.settings.RSS_COLLECTION_INTERVAL", 0)
    monkeypatch.setattr("src.core.source_freshness.settings.GDELT_COLLECTION_INTERVAL", 15)

    assert _collector_interval_minutes(SourceType.RSS) == 1
    assert _collector_interval_minutes(SourceType.GDELT) == 15
    assert _collector_interval_minutes(SourceType.TELEGRAM) is None


@pytest.mark.asyncio
async def test_build_source_freshness_report_marks_stale_sources(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)
    sources = [
        _build_source(
            name="RSS Fresh",
            source_type=SourceType.RSS,
            last_fetched_at=now - timedelta(minutes=30),
        ),
        _build_source(
            name="RSS Stale",
            source_type=SourceType.RSS,
            last_fetched_at=now - timedelta(hours=3),
        ),
        _build_source(
            name="GDELT Never",
            source_type=SourceType.GDELT,
            last_fetched_at=None,
        ),
    ]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: sources)
    monkeypatch.setattr("src.core.source_freshness.settings.RSS_COLLECTION_INTERVAL", 60)
    monkeypatch.setattr("src.core.source_freshness.settings.GDELT_COLLECTION_INTERVAL", 120)
    monkeypatch.setattr("src.core.source_freshness.settings.SOURCE_FRESHNESS_ALERT_MULTIPLIER", 2.0)

    report = await build_source_freshness_report(session=mock_db_session, checked_at=now)

    assert report.stale_count == 2
    assert report.stale_collectors == ("gdelt", "rss")
    rows_by_name = {row.source_name: row for row in report.rows}
    assert rows_by_name["RSS Fresh"].is_stale is False
    assert rows_by_name["RSS Fresh"].stale_after_seconds == 7200
    assert rows_by_name["RSS Stale"].is_stale is True
    assert rows_by_name["RSS Stale"].age_seconds == 10800
    assert rows_by_name["GDELT Never"].is_stale is True
    assert rows_by_name["GDELT Never"].age_seconds is None
    assert rows_by_name["GDELT Never"].stale_after_seconds == 14400


@pytest.mark.asyncio
async def test_build_source_freshness_report_respects_multiplier_override(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)
    source = _build_source(
        name="RSS Borderline",
        source_type=SourceType.RSS,
        last_fetched_at=now - timedelta(minutes=61),
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [source])
    monkeypatch.setattr("src.core.source_freshness.settings.RSS_COLLECTION_INTERVAL", 60)
    monkeypatch.setattr("src.core.source_freshness.settings.SOURCE_FRESHNESS_ALERT_MULTIPLIER", 2.0)

    default_report = await build_source_freshness_report(session=mock_db_session, checked_at=now)
    strict_report = await build_source_freshness_report(
        session=mock_db_session,
        checked_at=now,
        stale_multiplier=1.0,
    )

    assert default_report.rows[0].is_stale is False
    assert default_report.rows[0].stale_after_seconds == 7200
    assert strict_report.rows[0].is_stale is True
    assert strict_report.rows[0].stale_after_seconds == 3600


@pytest.mark.asyncio
async def test_build_source_freshness_report_skips_unknown_collectors_and_missing_ids(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 2, 16, 12, 0, tzinfo=UTC).replace(tzinfo=None)
    valid_source = _build_source(
        name="RSS Valid",
        source_type=SourceType.RSS,
        last_fetched_at=now,
    )
    skipped_source = _build_source(
        name="GDELT Missing ID",
        source_type=SourceType.GDELT,
        last_fetched_at=now,
    )
    skipped_source.id = None
    unsupported_source = _build_source(
        name="Telegram",
        source_type=SourceType.TELEGRAM,
        last_fetched_at=now,
    )
    mock_db_session.scalars.return_value = SimpleNamespace(
        all=lambda: [unsupported_source, skipped_source, valid_source]
    )
    monkeypatch.setattr("src.core.source_freshness.settings.RSS_COLLECTION_INTERVAL", 30)
    monkeypatch.setattr("src.core.source_freshness.settings.GDELT_COLLECTION_INTERVAL", 45)
    monkeypatch.setattr("src.core.source_freshness.settings.SOURCE_FRESHNESS_ALERT_MULTIPLIER", 0.5)

    report = await build_source_freshness_report(session=mock_db_session, checked_at=now)

    assert report.checked_at.tzinfo is UTC
    assert report.stale_multiplier == 1.0
    assert [row.source_name for row in report.rows] == ["RSS Valid"]
    assert report.rows[0].age_seconds == 0
