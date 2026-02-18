from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from src.api.routes.events import list_events
from src.storage.database import async_session_maker
from src.storage.models import Event, Source, SourceType

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_sources_reject_invalid_dimension_values() -> None:
    async with async_session_maker() as session:
        bad_source_tier = Source(
            type=SourceType.RSS,
            name="Bad source tier",
            url="https://example.com/feed",
            source_tier="invalid-tier",
            reporting_type="secondary",
        )
        session.add(bad_source_tier)

        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

        bad_reporting_type = Source(
            type=SourceType.RSS,
            name="Bad reporting type",
            url="https://example.com/feed-2",
            source_tier="wire",
            reporting_type="invalid-reporting",
        )
        session.add(bad_reporting_type)

        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_events_reject_invalid_lifecycle_status() -> None:
    async with async_session_maker() as session:
        bad_event = Event(
            canonical_summary="Bad lifecycle test",
            categories=["security"],
            source_count=1,
            unique_source_count=1,
            lifecycle_status="invalid-lifecycle",
        )
        session.add(bad_event)

        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_list_events_lifecycle_filter_still_returns_expected_rows() -> None:
    now = datetime.now(tz=UTC)
    async with async_session_maker() as session:
        confirmed_event = Event(
            canonical_summary="Confirmed event",
            categories=["security"],
            source_count=2,
            unique_source_count=2,
            lifecycle_status="confirmed",
            first_seen_at=now - timedelta(hours=6),
            last_mention_at=now - timedelta(minutes=15),
        )
        emerging_event = Event(
            canonical_summary="Emerging event",
            categories=["security"],
            source_count=1,
            unique_source_count=1,
            lifecycle_status="emerging",
            first_seen_at=now - timedelta(hours=3),
            last_mention_at=now - timedelta(minutes=5),
        )
        session.add_all([confirmed_event, emerging_event])
        await session.commit()

        events = await list_events(
            lifecycle="confirmed",
            contradicted=None,
            days=7,
            limit=10,
            session=session,
        )

        assert [event.id for event in events] == [confirmed_event.id]
