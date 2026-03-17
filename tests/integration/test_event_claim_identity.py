from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.trend_engine import TrendEngine
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.storage.database import async_session_maker
from src.storage.models import Event, EventClaim, Trend, TrendEvidence

pytestmark = pytest.mark.integration


def _pipeline(session) -> ProcessingPipeline:
    pipeline = ProcessingPipeline(
        session=session,
        deduplication_service=SimpleNamespace(),
        embedding_service=SimpleNamespace(),
        event_clusterer=SimpleNamespace(),
        tier1_classifier=SimpleNamespace(),
        tier2_classifier=SimpleNamespace(),
        trend_engine=TrendEngine(session=session),
    )
    pipeline._load_event_source_credibility = AsyncMock(return_value=0.8)
    pipeline._novelty_score = AsyncMock(return_value=1.0)
    pipeline._capture_taxonomy_gap = AsyncMock(return_value=None)
    pipeline._corroboration_score = AsyncMock(return_value=1.0)
    return pipeline


@pytest.mark.asyncio
async def test_contradictory_claims_share_event_but_get_distinct_claim_identity() -> None:
    now = datetime.now(tz=UTC)

    async with async_session_maker() as session:
        runtime_trend_id = f"claim-identity-{uuid4()}"
        trend = Trend(
            name=f"Claim Identity Trend {uuid4()}",
            description="Integration trend for stable event-claim identity",
            runtime_trend_id=runtime_trend_id,
            definition={"id": runtime_trend_id},
            baseline_log_odds=0.0,
            current_log_odds=0.0,
            indicators={
                "military_movement": {
                    "weight": 0.04,
                    "direction": "escalatory",
                    "keywords": ["troops"],
                }
            },
            decay_half_life_days=30,
            is_active=True,
        )
        event = Event(
            canonical_summary="Conflicting reports on city entry",
            source_count=2,
            unique_source_count=2,
            first_seen_at=now - timedelta(minutes=20),
            last_mention_at=now - timedelta(minutes=5),
            extracted_when=now,
            has_contradictions=True,
            contradiction_notes="One source claims entry while another denies it.",
            extracted_claims={
                "claims": [
                    "Troops advanced into the city",
                    "Troops did not advance into the city",
                ],
                "claim_graph": {
                    "nodes": [
                        {
                            "claim_id": "claim_1",
                            "text": "Troops advanced into the city",
                            "normalized_text": "troops advanced into the city",
                        },
                        {
                            "claim_id": "claim_2",
                            "text": "Troops did not advance into the city",
                            "normalized_text": "troops did not advance into the city",
                        },
                    ],
                    "links": [
                        {
                            "source_claim_id": "claim_1",
                            "target_claim_id": "claim_2",
                            "relation": "contradict",
                        }
                    ],
                },
                "trend_impacts": [
                    {
                        "trend_id": runtime_trend_id,
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.8,
                        "confidence": 0.9,
                        "rationale": "Troops advanced into the city",
                    }
                ],
            },
        )
        session.add_all([trend, event])
        await session.flush()

        pipeline = _pipeline(session)
        seen, updates = await pipeline._apply_trend_impacts(event=event, trends=[trend])
        await session.commit()

        claims = list(
            (
                await session.scalars(
                    select(EventClaim)
                    .where(EventClaim.event_id == event.id)
                    .order_by(EventClaim.claim_order.asc(), EventClaim.created_at.asc())
                )
            ).all()
        )
        evidence = await session.scalar(
            select(TrendEvidence)
            .where(TrendEvidence.event_id == event.id)
            .where(TrendEvidence.is_invalidated.is_(False))
            .limit(1)
        )

        assert seen == 1
        assert updates == 1
        assert evidence is not None
        assert len(claims) == 3

        fallback_claim = next(row for row in claims if row.claim_key == "__event__")
        positive_claim = next(
            row for row in claims if row.claim_text == "Troops advanced into the city"
        )
        negative_claim = next(
            row for row in claims if row.claim_text == "Troops did not advance into the city"
        )

        assert evidence.event_claim_id == positive_claim.id
        assert positive_claim.id != negative_claim.id
        assert fallback_claim.id != positive_claim.id

        impacts = (event.extracted_claims or {}).get("trend_impacts", [])
        assert impacts[0]["event_claim_id"] == str(positive_claim.id)
        assert impacts[0]["event_claim_text"] == positive_claim.claim_text
