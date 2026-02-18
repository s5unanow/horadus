from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.api.routes.events import list_events
from src.storage.database import async_session_maker
from src.storage.models import Event, Trend, TrendEvidence

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_list_events_trend_filter_deduplicates_multi_evidence_rows() -> None:
    now = datetime.now(tz=UTC)

    async with async_session_maker() as session:
        trend = Trend(
            name=f"Events API Trend {uuid4()}",
            description="Integration trend for events API de-duplication",
            definition={"id": "events-api-trend"},
            baseline_log_odds=-2.0,
            current_log_odds=-2.0,
            indicators={
                "signal_primary": {
                    "weight": 0.04,
                    "direction": "escalatory",
                    "keywords": ["alpha"],
                },
                "signal_secondary": {
                    "weight": 0.03,
                    "direction": "escalatory",
                    "keywords": ["beta"],
                },
            },
            decay_half_life_days=30,
            is_active=True,
        )
        newest_event = Event(
            canonical_summary="Newest matching event",
            categories=["security"],
            source_count=2,
            unique_source_count=2,
            lifecycle_status="confirmed",
            first_seen_at=now - timedelta(hours=4),
            last_mention_at=now - timedelta(minutes=10),
        )
        older_event = Event(
            canonical_summary="Older matching event",
            categories=["security"],
            source_count=1,
            unique_source_count=1,
            lifecycle_status="confirmed",
            first_seen_at=now - timedelta(hours=12),
            last_mention_at=now - timedelta(hours=2),
        )
        session.add_all([trend, newest_event, older_event])
        await session.flush()

        session.add_all(
            [
                TrendEvidence(
                    trend_id=trend.id,
                    event_id=newest_event.id,
                    signal_type="signal_primary",
                    delta_log_odds=0.12,
                ),
                TrendEvidence(
                    trend_id=trend.id,
                    event_id=newest_event.id,
                    signal_type="signal_secondary",
                    delta_log_odds=0.08,
                ),
                TrendEvidence(
                    trend_id=trend.id,
                    event_id=older_event.id,
                    signal_type="signal_primary",
                    delta_log_odds=0.05,
                ),
            ]
        )
        await session.commit()

        first_page = await list_events(
            trend_id=trend.id,
            contradicted=None,
            days=7,
            limit=1,
            session=session,
        )
        assert len(first_page) == 1
        assert first_page[0].id == newest_event.id

        full_page = await list_events(
            trend_id=trend.id,
            contradicted=None,
            days=7,
            limit=10,
            session=session,
        )
        assert [event.id for event in full_page] == [newest_event.id, older_event.id]
