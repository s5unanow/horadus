from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, literal, select

import src.processing.pipeline_orchestrator as orchestrator_module
from src.core.trend_engine import TrendUpdate
from src.processing.cost_tracker import BudgetExceededError
from src.processing.deduplication_service import DeduplicationResult
from src.processing.event_clusterer import ClusterResult
from src.processing.pipeline_orchestrator import (
    PipelineRunResult,
    PipelineUsage,
    ProcessingPipeline,
)
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2EventResult, Tier2Usage
from src.storage.models import Event, ProcessingStatus, RawItem, TaxonomyGap, TaxonomyGapReason

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


def _build_item_with_title(title: str) -> RawItem:
    item = _build_item()
    item.title = title
    return item


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
    mock_db_session.scalar = AsyncMock(side_effect=[event, None])

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
async def test_process_items_sets_item_embedding_lineage_when_embedding_created(
    mock_db_session,
) -> None:
    item = _build_item()
    event = Event(id=uuid4(), canonical_summary="Seed summary")

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(
        model="test-embedding-model",
        embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)),
    )
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
                Tier2Usage(prompt_tokens=10, completion_tokens=4, api_calls=1),
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
    )

    await pipeline.process_items([item], trends=[_build_trend()])

    assert item.embedding == [0.1, 0.2, 0.3]
    assert item.embedding_model == "test-embedding-model"
    assert item.embedding_generated_at is not None


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
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True)],
                Tier1Usage(prompt_tokens=10, completion_tokens=4, api_calls=1),
            )
        )
    )
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
async def test_process_items_batches_tier1_and_preserves_result_order(mock_db_session) -> None:
    item_one = _build_item_with_title("Pipeline item one")
    item_two = _build_item_with_title("Pipeline item two")
    event_one = Event(id=uuid4(), canonical_summary="Seed summary one")
    event_two = Event(id=uuid4(), canonical_summary="Seed summary two")

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            side_effect=[
                ClusterResult(
                    item_id=item_one.id,
                    event_id=event_one.id,
                    created=True,
                    merged=False,
                ),
                ClusterResult(
                    item_id=item_two.id,
                    event_id=event_two.id,
                    created=True,
                    merged=False,
                ),
            ]
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [
                    Tier1ItemResult(
                        item_id=item_one.id,
                        max_relevance=8,
                        should_queue_tier2=True,
                    ),
                    Tier1ItemResult(
                        item_id=item_two.id,
                        max_relevance=2,
                        should_queue_tier2=False,
                    ),
                ],
                Tier1Usage(prompt_tokens=20, completion_tokens=8, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(
                    event_id=event_one.id,
                    categories_count=1,
                    trend_impacts_count=1,
                ),
                Tier2Usage(prompt_tokens=15, completion_tokens=5, api_calls=1),
            )
        )
    )
    mock_db_session.scalar = AsyncMock(side_effect=[event_one, None, event_two, None])

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )

    result = await pipeline.process_items([item_one, item_two], trends=[_build_trend()])

    assert result.scanned == 2
    assert result.processed == 2
    assert result.classified == 1
    assert result.noise == 1
    assert result.errors == 0
    assert [row.item_id for row in result.results] == [item_one.id, item_two.id]
    assert result.results[0].final_status == ProcessingStatus.CLASSIFIED
    assert result.results[1].final_status == ProcessingStatus.NOISE
    assert tier1.classify_items.await_count == 1
    tier1_call = tier1.classify_items.await_args
    assert [row.id for row in tier1_call.args[0]] == [item_one.id, item_two.id]
    tier2.classify_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_items_tier1_batch_fallback_handles_partial_failures(mock_db_session) -> None:
    item_fail = _build_item_with_title("Pipeline item fail")
    item_ok = _build_item_with_title("Pipeline item ok")
    event_fail = Event(id=uuid4(), canonical_summary="Seed summary fail")
    event_ok = Event(id=uuid4(), canonical_summary="Seed summary ok")

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            side_effect=[
                ClusterResult(
                    item_id=item_fail.id,
                    event_id=event_fail.id,
                    created=True,
                    merged=False,
                ),
                ClusterResult(
                    item_id=item_ok.id,
                    event_id=event_ok.id,
                    created=True,
                    merged=False,
                ),
            ]
        )
    )

    async def classify_items(items, trends):
        _ = trends
        if len(items) > 1:
            raise ValueError("Tier 1 response item ids do not match input batch")

        current_item = items[0]
        if current_item.id == item_fail.id:
            raise ValueError("Tier 1 response trend ids mismatch for item")

        return (
            [
                Tier1ItemResult(
                    item_id=current_item.id,
                    max_relevance=1,
                    should_queue_tier2=False,
                )
            ],
            Tier1Usage(prompt_tokens=4, completion_tokens=2, api_calls=1),
        )

    tier1 = SimpleNamespace(classify_items=AsyncMock(side_effect=classify_items))
    tier2 = SimpleNamespace(classify_event=AsyncMock())
    mock_db_session.scalar = AsyncMock(side_effect=[event_fail, None, event_ok, None])

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )

    result = await pipeline.process_items([item_fail, item_ok], trends=[_build_trend()])

    assert result.scanned == 2
    assert result.processed == 1
    assert result.classified == 0
    assert result.noise == 1
    assert result.errors == 1
    assert result.results[0].final_status == ProcessingStatus.ERROR
    assert result.results[1].final_status == ProcessingStatus.NOISE
    assert item_fail.processing_status == ProcessingStatus.ERROR
    assert item_ok.processing_status == ProcessingStatus.NOISE
    assert tier1.classify_items.await_count == 3
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
    mock_db_session.scalar = AsyncMock(side_effect=[event, None, None])

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
async def test_corroboration_score_prevents_derivative_overcount(mock_db_session) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Corroboration test",
        source_count=5,
        unique_source_count=5,
    )
    rows = [
        (uuid4(), "wire", "aggregator"),
        (uuid4(), "wire", "aggregator"),
        (uuid4(), "wire", "aggregator"),
        (uuid4(), "wire", "aggregator"),
        (uuid4(), "wire", "firsthand"),
    ]
    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=SimpleNamespace(),
        embedding_service=SimpleNamespace(),
        event_clusterer=SimpleNamespace(),
        tier1_classifier=SimpleNamespace(),
        tier2_classifier=SimpleNamespace(),
        trend_engine=SimpleNamespace(),
    )

    score = await pipeline._corroboration_score(event)

    assert score == pytest.approx(1.35, rel=0.01)
    assert score < 5.0


@pytest.mark.asyncio
async def test_corroboration_score_parses_sqlalchemy_rows(
    mock_db_session,
    monkeypatch,
) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Corroboration row parsing test",
        source_count=2,
        unique_source_count=2,
    )
    with create_engine("sqlite+pysqlite:///:memory:").connect() as connection:
        row_aggregator = connection.execute(
            select(
                literal(str(uuid4())).label("source_id"),
                literal("wire").label("source_tier"),
                literal("aggregator").label("reporting_type"),
            )
        ).one()
        row_firsthand = connection.execute(
            select(
                literal(str(uuid4())).label("source_id"),
                literal("wire").label("source_tier"),
                literal("firsthand").label("reporting_type"),
            )
        ).one()
    mock_db_session.execute = AsyncMock(
        return_value=SimpleNamespace(all=lambda: [row_aggregator, row_firsthand])
    )
    corroboration_path_calls: list[tuple[str, str]] = []

    def _record_path(*, mode: str, reason: str) -> None:
        corroboration_path_calls.append((mode, reason))

    monkeypatch.setattr(orchestrator_module, "record_processing_corroboration_path", _record_path)

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=SimpleNamespace(),
        embedding_service=SimpleNamespace(),
        event_clusterer=SimpleNamespace(),
        tier1_classifier=SimpleNamespace(),
        tier2_classifier=SimpleNamespace(),
        trend_engine=SimpleNamespace(),
    )

    score = await pipeline._corroboration_score(event)

    assert score == pytest.approx(1.35, rel=0.01)
    assert corroboration_path_calls == [("cluster_aware", "source_cluster_fields_present")]


@pytest.mark.asyncio
async def test_corroboration_score_falls_back_when_source_id_absent(
    mock_db_session,
    monkeypatch,
) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Fallback corroboration test",
        source_count=4,
        unique_source_count=4,
    )
    with create_engine("sqlite+pysqlite:///:memory:").connect() as connection:
        malformed_row = connection.execute(
            select(
                literal("wire").label("source_tier"),
                literal("aggregator").label("reporting_type"),
            )
        ).one()
    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: [malformed_row]))
    corroboration_path_calls: list[tuple[str, str]] = []

    def _record_path(*, mode: str, reason: str) -> None:
        corroboration_path_calls.append((mode, reason))

    monkeypatch.setattr(orchestrator_module, "record_processing_corroboration_path", _record_path)

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=SimpleNamespace(),
        embedding_service=SimpleNamespace(),
        event_clusterer=SimpleNamespace(),
        tier1_classifier=SimpleNamespace(),
        tier2_classifier=SimpleNamespace(),
        trend_engine=SimpleNamespace(),
    )

    score = await pipeline._corroboration_score(event)

    assert score == pytest.approx(4.0, rel=0.01)
    assert corroboration_path_calls == [("fallback", "missing_source_cluster_fields")]


@pytest.mark.asyncio
async def test_corroboration_score_applies_contradiction_penalty(mock_db_session) -> None:
    rows = [
        (uuid4(), "wire", "firsthand"),
        (uuid4(), "major", "firsthand"),
    ]
    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=SimpleNamespace(),
        embedding_service=SimpleNamespace(),
        event_clusterer=SimpleNamespace(),
        tier1_classifier=SimpleNamespace(),
        tier2_classifier=SimpleNamespace(),
        trend_engine=SimpleNamespace(),
    )

    baseline_event = Event(id=uuid4(), canonical_summary="Baseline")
    contradiction_event = Event(
        id=uuid4(),
        canonical_summary="Contradiction",
        has_contradictions=True,
        extracted_claims={
            "claim_graph": {
                "links": [
                    {"relation": "contradict"},
                    {"relation": "contradict"},
                ]
            }
        },
    )

    baseline_score = await pipeline._corroboration_score(baseline_event)
    contradiction_score = await pipeline._corroboration_score(contradiction_event)

    assert baseline_score == pytest.approx(2.0, rel=0.01)
    assert contradiction_score == pytest.approx(1.4, rel=0.01)
    assert contradiction_score < baseline_score


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
    assert result.trend_updates == 0
    gap_record = mock_db_session.add.call_args.args[0]
    assert isinstance(gap_record, TaxonomyGap)
    assert gap_record.reason == TaxonomyGapReason.UNKNOWN_SIGNAL_TYPE
    assert gap_record.trend_id == "eu-russia"
    assert gap_record.signal_type == "unknown_signal"


@pytest.mark.asyncio
async def test_process_items_records_taxonomy_gap_for_unknown_trend_id(mock_db_session) -> None:
    item = _build_item()
    trend = _build_trend()
    event = Event(
        id=uuid4(),
        canonical_summary="Seed summary",
        extracted_claims={
            "trend_impacts": [
                {
                    "trend_id": "unknown-trend",
                    "signal_type": "military_movement",
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
    assert result.trend_updates == 0
    gap_record = mock_db_session.add.call_args.args[0]
    assert isinstance(gap_record, TaxonomyGap)
    assert gap_record.reason == TaxonomyGapReason.UNKNOWN_TREND_ID
    assert gap_record.trend_id == "unknown-trend"
    assert gap_record.signal_type == "military_movement"


@pytest.mark.asyncio
async def test_process_items_applies_indicator_decay_factor(mock_db_session) -> None:
    item = _build_item()
    trend = _build_trend()
    trend.decay_half_life_days = 30
    trend.indicators["military_movement"]["decay_half_life_days"] = 7

    event = Event(
        id=uuid4(),
        canonical_summary="Seed summary",
        extracted_when=datetime.now(tz=UTC) - timedelta(days=14),
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
        source_count=3,
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
                new_probability=0.11,
                delta_applied=0.01,
                direction="up",
            )
        )
    )
    mock_db_session.scalar = AsyncMock(side_effect=[event, None, None])

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
        trend_engine=mock_trend_engine,
    )

    await pipeline.process_items([item], trends=[trend])

    call = mock_trend_engine.apply_evidence.await_args
    factors = call.kwargs["factors"]
    assert factors.evidence_age_days == pytest.approx(14.0, rel=0.05)
    assert factors.temporal_decay_multiplier == pytest.approx(0.25, rel=0.05)
    mock_trend_engine.apply_evidence.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_items_keeps_item_pending_when_tier1_budget_exceeded(mock_db_session) -> None:
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
            side_effect=BudgetExceededError("tier1 daily call limit (1) exceeded")
        )
    )
    tier2 = SimpleNamespace(classify_event=AsyncMock())
    mock_db_session.scalar = AsyncMock(side_effect=[event, None])

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
    assert result.errors == 0
    assert result.classified == 0
    assert result.noise == 0
    assert result.results[0].final_status == ProcessingStatus.PENDING
    assert item.processing_status == ProcessingStatus.PENDING
    tier2.classify_event.assert_not_called()


@pytest.mark.asyncio
async def test_process_items_keeps_item_pending_when_tier2_budget_exceeded(mock_db_session) -> None:
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
            side_effect=BudgetExceededError("tier2 daily call limit (1) exceeded")
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
    )

    result = await pipeline.process_items([item], trends=[_build_trend()])

    assert result.scanned == 1
    assert result.processed == 0
    assert result.errors == 0
    assert result.classified == 0
    assert result.results[0].final_status == ProcessingStatus.PENDING
    assert item.processing_status == ProcessingStatus.PENDING


@pytest.mark.asyncio
async def test_process_items_skips_event_marked_as_noise_feedback(mock_db_session) -> None:
    item = _build_item()
    event = Event(id=uuid4(), canonical_summary="Suppressed event")

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
    embedding = SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1, 0.2, 0.3]], 0, 1)))
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            return_value=ClusterResult(
                item_id=item.id,
                event_id=event.id,
                created=False,
                merged=True,
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
    tier2 = SimpleNamespace(classify_event=AsyncMock())
    mock_db_session.scalar = AsyncMock(side_effect=[event, "mark_noise"])

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
    assert result.noise == 1
    assert result.classified == 0
    assert result.errors == 0
    assert item.processing_status == ProcessingStatus.NOISE
    tier1.classify_items.assert_awaited_once()
    tier2.classify_event.assert_not_called()


def test_processing_pipeline_legacy_process_item_path_removed() -> None:
    assert not hasattr(ProcessingPipeline, "_process_item")


def test_run_result_to_dict_includes_estimated_cost_fields() -> None:
    run_result = PipelineRunResult(
        usage=PipelineUsage(
            embedding_api_calls=2,
            embedding_estimated_cost_usd=0.00001,
            tier1_prompt_tokens=100,
            tier1_completion_tokens=20,
            tier1_api_calls=1,
            tier1_estimated_cost_usd=0.00002,
            tier2_prompt_tokens=80,
            tier2_completion_tokens=40,
            tier2_api_calls=1,
            tier2_estimated_cost_usd=0.00003,
        )
    )

    payload = ProcessingPipeline.run_result_to_dict(run_result)

    assert payload["embedding_estimated_cost_usd"] == pytest.approx(0.00001)
    assert payload["tier1_estimated_cost_usd"] == pytest.approx(0.00002)
    assert payload["tier2_estimated_cost_usd"] == pytest.approx(0.00003)


@pytest.mark.asyncio
async def test_process_items_skips_unsupported_language_when_mode_skip(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator_module.settings, "LANGUAGE_POLICY_SUPPORTED_LANGUAGES", ["en", "uk", "ru"]
    )
    monkeypatch.setattr(orchestrator_module.settings, "LANGUAGE_POLICY_UNSUPPORTED_MODE", "skip")
    item = _build_item()
    item.language = "es"

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
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
    assert result.noise == 1
    assert result.classified == 0
    assert result.results[0].final_status == ProcessingStatus.NOISE
    assert item.error_message == "unsupported_language:es:skip"
    embedding.embed_texts.assert_not_called()
    clusterer.cluster_item.assert_not_called()
    tier1.classify_items.assert_not_called()
    tier2.classify_event.assert_not_called()


@pytest.mark.asyncio
async def test_process_items_defers_unsupported_language_when_mode_defer(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator_module.settings, "LANGUAGE_POLICY_SUPPORTED_LANGUAGES", ["en", "uk", "ru"]
    )
    monkeypatch.setattr(orchestrator_module.settings, "LANGUAGE_POLICY_UNSUPPORTED_MODE", "defer")
    item = _build_item()
    item.language = "fr"

    dedup = SimpleNamespace(find_duplicate=AsyncMock(return_value=DeduplicationResult(False)))
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
    assert result.processed == 0
    assert result.noise == 0
    assert result.classified == 0
    assert result.results[0].final_status == ProcessingStatus.PENDING
    assert item.error_message == "unsupported_language:fr:defer"
    embedding.embed_texts.assert_not_called()
    clusterer.cluster_item.assert_not_called()
    tier1.classify_items.assert_not_called()
    tier2.classify_event.assert_not_called()


@pytest.mark.asyncio
async def test_process_items_records_language_segmented_metrics(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _build_item()
    item.language = "uk"
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
                [Tier1ItemResult(item_id=item.id, max_relevance=9, should_queue_tier2=True)],
                Tier1Usage(prompt_tokens=1, completion_tokens=1, api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(event_id=event.id, categories_count=1, trend_impacts_count=1),
                Tier2Usage(prompt_tokens=1, completion_tokens=1, api_calls=1),
            )
        )
    )
    mock_db_session.scalar = AsyncMock(side_effect=[event, None])

    ingested: list[str] = []
    tier1_outcomes: list[tuple[str, str]] = []
    tier2_usage: list[str] = []
    monkeypatch.setattr(
        orchestrator_module,
        "record_processing_ingested_language",
        lambda *, language: ingested.append(language),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "record_processing_tier1_language_outcome",
        lambda *, language, outcome: tier1_outcomes.append((language, outcome)),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "record_processing_tier2_language_usage",
        lambda *, language: tier2_usage.append(language),
    )

    pipeline = ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=dedup,
        embedding_service=embedding,
        event_clusterer=clusterer,
        tier1_classifier=tier1,
        tier2_classifier=tier2,
    )
    result = await pipeline.process_items([item], trends=[_build_trend()])

    assert result.classified == 1
    assert ingested == ["uk"]
    assert tier1_outcomes == [("uk", "pass")]
    assert tier2_usage == ["uk"]
