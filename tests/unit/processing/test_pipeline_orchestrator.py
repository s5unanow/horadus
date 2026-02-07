from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.trend_engine import TrendUpdate
from src.processing.deduplication_service import DeduplicationResult
from src.processing.event_clusterer import ClusterResult
from src.processing.pipeline_orchestrator import ProcessingPipeline
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2EventResult, Tier2Usage
from src.storage.models import Event, ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


def _build_item() -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"external-{uuid4()}",
        url=f"https://example.test/{uuid4()}",
        title="Pipeline test item",
        raw_content="Troops moved near the border",
        content_hash="abc123",
        fetched_at=datetime.now(tz=UTC),
        processing_status=ProcessingStatus.PENDING,
    )


def _build_trend() -> object:
    return SimpleNamespace(
        id=uuid4(),
        name="EU-Russia",
        definition={"id": "eu-russia"},
        indicators={
            "military_movement": {
                "weight": 0.04,
                "direction": "escalatory",
                "keywords": ["troops"],
            }
        },
    )


@pytest.mark.asyncio
async def test_process_items_classifies_relevant_item(mock_db_session) -> None:
    item = _build_item()
    event = Event(id=uuid4(), canonical_summary="Seed summary")

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            return_value=ClusterResult(
                item_id=item.id,
                event_id=event.id,
                created=True,
                merged=False,
            )
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True)],
                Tier1Usage(prompt_tokens=10, completion_tokens=4, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(
                    event_id=event.id,
                    categories_count=1,
                    trend_impacts_count=1,
                ),
                Tier2Usage(prompt_tokens=20, completion_tokens=6, api_calls=1),
            )
        )
    )
    mock_db_session.scalar = AsyncMock(return_value=event)

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )

    result = await pipeline.process_items([item], trends=[_build_trend()])

    assert result.scanned == 1
    assert result.processed == 1
    assert result.classified == 1
    assert result.noise == 0
    assert result.errors == 0
    assert result.embedded == 1
    assert result.events_created == 1
    assert result.events_merged == 0
    assert result.trend_impacts_seen == 0
    assert result.trend_updates == 0
    assert result.usage.embedding_api_calls == 1
    assert result.usage.tier1_api_calls == 1
    assert result.usage.tier2_api_calls == 1
    assert item.processing_status == ProcessingStatus.CLASSIFIED
    assert item.error_message is None


@pytest.mark.asyncio
async def test_process_items_marks_duplicates_as_noise(mock_db_session) -> None:
    item = _build_item()
    dedup = SimpleNamespace(
        find_duplicate=AsyncMock(
            return_value=DeduplicationResult(
                is_duplicate=True,
                matched_item_id=uuid4(),
                match_reason="content_hash",
            )
        )
    )
    embedding = SimpleNamespace(embed_texts=AsyncMock())
    clusterer = SimpleNamespace(cluster_item=AsyncMock())
    tier1 = SimpleNamespace(classify_items=AsyncMock())
    tier2 = SimpleNamespace(classify_event=AsyncMock())

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )

    result = await pipeline.process_items([item], trends=[_build_trend()])

    assert result.scanned == 1
    assert result.processed == 1
    assert result.classified == 0
    assert result.noise == 1
    assert result.duplicates == 1
    assert result.errors == 0
    assert result.trend_impacts_seen == 0
    assert result.trend_updates == 0
    assert item.processing_status == ProcessingStatus.NOISE
    embedding.embed_texts.assert_not_called()
    clusterer.cluster_item.assert_not_called()
    tier1.classify_items.assert_not_called()
    tier2.classify_event.assert_not_called()


@pytest.mark.asyncio
async def test_process_items_sets_error_status_on_failure(mock_db_session) -> None:
    item = _build_item()
    event_id = uuid4()

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            return_value=ClusterResult(
                item_id=item.id,
                event_id=event_id,
                created=False,
                merged=True,
            )
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [Tier1ItemResult(item_id=item.id, max_relevance=9, should_queue_tier2=True)],
                Tier1Usage(prompt_tokens=3, completion_tokens=2, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(classify_event=AsyncMock())
    mock_db_session.scalar = AsyncMock(return_value=None)

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )

    result = await pipeline.process_items([item], trends=[_build_trend()])

    assert result.scanned == 1
    assert result.processed == 0
    assert result.errors == 1
    assert result.trend_impacts_seen == 0
    assert result.trend_updates == 0
    assert item.processing_status == ProcessingStatus.ERROR
    assert item.error_message is not None
    tier2.classify_event.assert_not_called()


@pytest.mark.asyncio
async def test_process_items_applies_trend_impacts(mock_db_session) -> None:
    item = _build_item()
    trend = _build_trend()
    event = Event(
        id=uuid4(),
        canonical_summary="Seed summary",
        extracted_claims={
            "trend_impacts": [
                {
                    "trend_id": "eu-russia",
                    "signal_type": "military_movement",
                    "direction": "escalatory",
                    "severity": 0.8,
                    "confidence": 0.9,
                    "rationale": "Visible force buildup pattern",
                }
            ]
        },
        unique_source_count=3,
    )

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            return_value=ClusterResult(
                item_id=item.id,
                event_id=event.id,
                created=True,
                merged=False,
            )
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True)],
                Tier1Usage(prompt_tokens=10, completion_tokens=4, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(
                    event_id=event.id,
                    categories_count=1,
                    trend_impacts_count=1,
                ),
                Tier2Usage(prompt_tokens=20, completion_tokens=6, api_calls=1),
            )
        )
    )
    mock_trend_engine = SimpleNamespace(
        apply_evidence=AsyncMock(
            return_value=TrendUpdate(
                previous_probability=0.10,
                new_probability=0.12,
                delta_applied=0.02,
                direction="up",
            )
        )
    )
    mock_db_session.scalar = AsyncMock(side_effect=[event, None])

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
        trend_engine=mock_trend_engine,
    )

    result = await pipeline.process_items([item], trends=[trend])

    assert result.scanned == 1
    assert result.processed == 1
    assert result.classified == 1
    assert result.errors == 0
    assert result.trend_impacts_seen == 1
    assert result.trend_updates == 1
    assert result.results[0].trend_impacts_seen == 1
    assert result.results[0].trend_updates == 1
    mock_trend_engine.apply_evidence.assert_awaited_once()
    call = mock_trend_engine.apply_evidence.await_args
    factors = call.kwargs["factors"]
    assert call.kwargs["trend"] is trend
    assert call.kwargs["event_id"] == event.id
    assert call.kwargs["signal_type"] == "military_movement"
    assert call.kwargs["reasoning"] == "Visible force buildup pattern"
    assert factors.base_weight == pytest.approx(0.04)
    assert factors.credibility == pytest.approx(0.5)
    assert factors.corroboration == pytest.approx((3**0.5) / 3, rel=0.01)
    assert factors.novelty == pytest.approx(1.0)
    assert factors.severity == pytest.approx(0.8)
    assert factors.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_process_items_skips_unknown_signal_weight(mock_db_session) -> None:
    item = _build_item()
    trend = _build_trend()
    event = Event(
        id=uuid4(),
        canonical_summary="Seed summary",
        extracted_claims={
            "trend_impacts": [
                {
                    "trend_id": "eu-russia",
                    "signal_type": "unknown_signal",
                    "direction": "escalatory",
                    "severity": 0.7,
                    "confidence": 0.8,
                }
            ]
        },
    )

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            return_value=ClusterResult(
                item_id=item.id,
                event_id=event.id,
                created=True,
                merged=False,
            )
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True)],
                Tier1Usage(prompt_tokens=10, completion_tokens=4, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(
                    event_id=event.id,
                    categories_count=1,
                    trend_impacts_count=1,
                ),
                Tier2Usage(prompt_tokens=20, completion_tokens=6, api_calls=1),
            )
        )
    )
    mock_trend_engine = SimpleNamespace(apply_evidence=AsyncMock())
    mock_db_session.scalar = AsyncMock(return_value=event)

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
        trend_engine=mock_trend_engine,
    )

    result = await pipeline.process_items([item], trends=[trend])

    assert result.scanned == 1
    assert result.processed == 1
    assert result.classified == 1
    assert result.errors == 0
    assert result.trend_impacts_seen == 1
    assert result.trend_updates == 0
    mock_trend_engine.apply_evidence.assert_not_called()
