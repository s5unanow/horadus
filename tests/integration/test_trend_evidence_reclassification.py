from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.trend_engine import EvidenceFactors, TrendEngine
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.storage.database import async_session_maker
from src.storage.models import Event, Trend, TrendEvidence

pytestmark = pytest.mark.integration


def _factors(
    *,
    severity: float,
    confidence: float,
    corroboration: float,
) -> EvidenceFactors:
    return EvidenceFactors(
        base_weight=0.04,
        severity=severity,
        confidence=confidence,
        credibility=0.8,
        corroboration=corroboration,
        novelty=1.0,
        evidence_age_days=0.0,
        temporal_decay_multiplier=1.0,
        direction_multiplier=1.0,
        raw_delta=0.0,
        clamped_delta=0.0,
    )


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
    return pipeline


@pytest.mark.asyncio
async def test_reclassification_supersedes_active_evidence_when_severity_changes() -> None:
    now = datetime.now(tz=UTC)

    async with async_session_maker() as session:
        runtime_trend_id = f"reclassify-{uuid4()}"
        trend = Trend(
            name=f"Reclassification Trend {uuid4()}",
            description="Integration trend for Tier-2 evidence reconciliation",
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
            canonical_summary="Escalation event",
            source_count=1,
            unique_source_count=1,
            first_seen_at=now - timedelta(minutes=5),
            last_mention_at=now - timedelta(minutes=5),
            extracted_when=now,
        )
        session.add_all([trend, event])
        await session.flush()

        engine = TrendEngine(session=session)
        await engine.apply_evidence(
            trend=trend,
            delta=0.05,
            event_id=event.id,
            signal_type="military_movement",
            factors=_factors(severity=0.4, confidence=0.6, corroboration=1.0),
            reasoning="Initial lower-severity classification",
        )
        await session.flush()

        pipeline = _pipeline(session)
        pipeline._corroboration_score = AsyncMock(return_value=1.0)
        event.extracted_claims = {
            "trend_impacts": [
                {
                    "trend_id": runtime_trend_id,
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.9,
                    "confidence": 0.95,
                    "rationale": "Force posture has intensified materially",
                }
            ]
        }

        seen, updates = await pipeline._apply_trend_impacts(event=event, trends=[trend])
        await session.commit()

        evidence_rows = list(
            (
                await session.scalars(
                    select(TrendEvidence)
                    .where(TrendEvidence.event_id == event.id)
                    .order_by(TrendEvidence.created_at.asc())
                )
            ).all()
        )
        active_row = next(row for row in evidence_rows if not row.is_invalidated)
        invalidated_row = next(row for row in evidence_rows if row.is_invalidated)

        assert seen == 1
        assert updates == 1
        assert len(evidence_rows) == 2
        assert invalidated_row.invalidated_at is not None
        assert float(active_row.severity_score or 0.0) == pytest.approx(0.9)
        assert active_row.reasoning == "Force posture has intensified materially"
        assert float(trend.current_log_odds) == pytest.approx(float(active_row.delta_log_odds))

        claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
        history = claims.get("_trend_impact_reconciliation")
        assert isinstance(history, list)
        assert len(history) == 1
        superseded = history[0]["superseded_evidence"]
        assert superseded[0]["evidence_id"] == str(invalidated_row.id)
        assert superseded[0]["change_type"] == "replaced"
        assert superseded[0]["replacement"]["severity"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_reclassification_supersedes_active_evidence_when_event_merge_changes_factors() -> (
    None
):
    now = datetime.now(tz=UTC)

    async with async_session_maker() as session:
        runtime_trend_id = f"merge-reclassify-{uuid4()}"
        trend = Trend(
            name=f"Merged Trend {uuid4()}",
            description="Integration trend for merged-event evidence reconciliation",
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
            canonical_summary="Merged event",
            source_count=3,
            unique_source_count=3,
            first_seen_at=now - timedelta(minutes=5),
            last_mention_at=now - timedelta(minutes=1),
            extracted_when=now,
            extracted_claims={
                "trend_impacts": [
                    {
                        "trend_id": runtime_trend_id,
                        "signal_type": "military_movement",
                        "direction": "escalatory",
                        "severity": 0.8,
                        "confidence": 0.9,
                        "rationale": "Merged evidence still indicates escalation",
                    }
                ]
            },
        )
        session.add_all([trend, event])
        await session.flush()

        engine = TrendEngine(session=session)
        await engine.apply_evidence(
            trend=trend,
            delta=0.04,
            event_id=event.id,
            signal_type="military_movement",
            factors=_factors(severity=0.8, confidence=0.9, corroboration=1 / 3),
            reasoning="Original single-source application",
        )
        await session.flush()

        pipeline = _pipeline(session)
        pipeline._corroboration_score = AsyncMock(return_value=2.0)

        seen, updates = await pipeline._apply_trend_impacts(event=event, trends=[trend])
        await session.commit()

        evidence_rows = list(
            (
                await session.scalars(
                    select(TrendEvidence)
                    .where(TrendEvidence.event_id == event.id)
                    .order_by(TrendEvidence.created_at.asc())
                )
            ).all()
        )
        active_row = next(row for row in evidence_rows if not row.is_invalidated)
        invalidated_row = next(row for row in evidence_rows if row.is_invalidated)

        assert seen == 1
        assert updates == 1
        assert len(evidence_rows) == 2
        assert float(active_row.corroboration_factor or 0.0) > float(
            invalidated_row.corroboration_factor or 0.0
        )
        assert float(trend.current_log_odds) == pytest.approx(float(active_row.delta_log_odds))
        assert invalidated_row.reasoning == "Original single-source application"
