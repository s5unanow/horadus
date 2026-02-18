from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.api.routes.feedback import EventFeedbackRequest, create_event_feedback
from src.api.routes.trends import list_trend_evidence
from src.storage.database import async_session_maker
from src.storage.models import Event, Trend, TrendEvidence

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_event_invalidation_preserves_evidence_lineage_and_reverses_delta() -> None:
    now = datetime.now(tz=UTC)

    async with async_session_maker() as session:
        trend = Trend(
            name=f"Invalidate Trend {uuid4()}",
            description="Integration trend for invalidation lineage",
            definition={"id": "invalidate-lineage"},
            baseline_log_odds=-2.0,
            current_log_odds=-1.5,
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
        event = Event(
            canonical_summary="Event later invalidated",
            categories=["security"],
            source_count=2,
            unique_source_count=2,
            lifecycle_status="confirmed",
            first_seen_at=now - timedelta(hours=3),
            last_mention_at=now - timedelta(minutes=20),
        )
        session.add_all([trend, event])
        await session.flush()

        evidence_one = TrendEvidence(
            trend_id=trend.id,
            event_id=event.id,
            signal_type="signal_primary",
            delta_log_odds=0.20,
            reasoning="Initial corroborated signal",
        )
        evidence_two = TrendEvidence(
            trend_id=trend.id,
            event_id=event.id,
            signal_type="signal_secondary",
            delta_log_odds=0.10,
            reasoning="Follow-on corroborated signal",
        )
        session.add_all([evidence_one, evidence_two])
        await session.commit()

        feedback = await create_event_feedback(
            event_id=event.id,
            payload=EventFeedbackRequest(
                action="invalidate",
                notes="Conflicting sources; invalidate for audit replay.",
                created_by="analyst@horadus",
            ),
            session=session,
        )
        await session.commit()

        refreshed_trend = await session.get(Trend, trend.id)
        assert refreshed_trend is not None
        assert float(refreshed_trend.current_log_odds) == pytest.approx(-1.8)

        evidence_rows = list(
            (
                await session.scalars(
                    select(TrendEvidence)
                    .where(TrendEvidence.event_id == event.id)
                    .order_by(TrendEvidence.signal_type.asc())
                )
            ).all()
        )
        assert len(evidence_rows) == 2
        assert all(row.is_invalidated for row in evidence_rows)
        assert all(row.invalidated_at is not None for row in evidence_rows)
        assert all(row.invalidation_feedback_id == feedback.id for row in evidence_rows)

        active_evidence = await list_trend_evidence(
            trend_id=trend.id,
            include_invalidated=False,
            session=session,
        )
        assert active_evidence == []

        lineage_evidence = await list_trend_evidence(
            trend_id=trend.id,
            include_invalidated=True,
            session=session,
        )
        assert len(lineage_evidence) == 2
        assert all(entry.is_invalidated for entry in lineage_evidence)
        assert all(entry.invalidation_feedback_id == feedback.id for entry in lineage_evidence)
