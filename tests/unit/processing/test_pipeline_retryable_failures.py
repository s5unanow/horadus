from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from src.processing.event_clusterer import ClusterResult
from src.processing.pipeline_orchestrator import ProcessingPipeline, _PreparedItem
from src.processing.pipeline_retry import RetryablePipelineError
from src.processing.tier1_classifier import Tier1ItemResult, Tier1Usage
from src.processing.tier2_classifier import Tier2EventResult, Tier2Usage
from src.storage.models import Event, ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


def _item() -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"ext-{uuid4()}",
        url=f"https://example.test/{uuid4()}",
        title="title",
        raw_content="content",
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PENDING,
    )


def _trend() -> object:
    return SimpleNamespace(
        id=uuid4(),
        name="EU-Russia",
        runtime_trend_id="eu-russia",
        definition={"id": "eu-russia"},
        indicators={"military_movement": {"weight": 0.04}},
    )


def _pipeline(mock_db_session, **overrides) -> ProcessingPipeline:
    return ProcessingPipeline(
        session=mock_db_session,
        deduplication_service=overrides.pop(
            "deduplication_service",
            SimpleNamespace(
                find_duplicate=AsyncMock(return_value=SimpleNamespace(is_duplicate=False))
            ),
        ),
        embedding_service=overrides.pop(
            "embedding_service",
            SimpleNamespace(embed_texts=AsyncMock(return_value=([[0.1]], 0, 1))),
        ),
        event_clusterer=overrides.pop(
            "event_clusterer",
            SimpleNamespace(
                cluster_item=AsyncMock(
                    return_value=ClusterResult(
                        item_id=uuid4(), event_id=uuid4(), created=True, merged=False
                    )
                )
            ),
        ),
        tier1_classifier=overrides.pop(
            "tier1_classifier",
            SimpleNamespace(
                classify_items=AsyncMock(
                    return_value=(
                        [
                            Tier1ItemResult(
                                item_id=uuid4(), max_relevance=8, should_queue_tier2=True
                            )
                        ],
                        Tier1Usage(api_calls=1),
                    )
                )
            ),
        ),
        tier2_classifier=overrides.pop(
            "tier2_classifier",
            SimpleNamespace(
                classify_event=AsyncMock(
                    return_value=(
                        SimpleNamespace(
                            event_id=uuid4(), categories_count=0, trend_impacts_count=0
                        ),
                        Tier2Usage(api_calls=1),
                    )
                )
            ),
        ),
        trend_engine=overrides.pop("trend_engine", SimpleNamespace(apply_evidence=AsyncMock())),
        degraded_llm_tracker=overrides.pop("degraded_llm_tracker", None),
    )


@pytest.mark.asyncio
async def test_prepare_item_for_tier1_raises_retryable_pipeline_error(mock_db_session) -> None:
    item = _item()
    pipeline = _pipeline(
        mock_db_session,
        deduplication_service=SimpleNamespace(
            find_duplicate=AsyncMock(side_effect=TimeoutError("retry"))
        ),
    )

    with pytest.raises(RetryablePipelineError, match="prepare"):
        await pipeline._prepare_item_for_tier1(item=item)

    assert item.processing_status == ProcessingStatus.PENDING
    assert item.processing_started_at is None
    assert item.error_message is None


@pytest.mark.asyncio
async def test_classify_tier1_prepared_items_raises_retryable_pipeline_error(
    mock_db_session,
) -> None:
    item_one = _item()
    item_two = _item()
    prepared_items = [
        _PreparedItem(item=item_one, item_id=item_one.id, raw_content=item_one.raw_content),
        _PreparedItem(item=item_two, item_id=item_two.id, raw_content=item_two.raw_content),
    ]
    pipeline = _pipeline(
        mock_db_session,
        tier1_classifier=SimpleNamespace(
            classify_items=AsyncMock(side_effect=ConnectionError("retry"))
        ),
    )

    with pytest.raises(RetryablePipelineError, match="tier1_batch"):
        await pipeline._classify_tier1_prepared_items(
            prepared_items=prepared_items, trends=[_trend()]
        )

    assert item_one.processing_status == ProcessingStatus.PENDING
    assert item_two.processing_status == ProcessingStatus.PENDING


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["embedding", "clustering", "tier2"])
async def test_process_after_tier1_raises_retryable_pipeline_error_for_transient_failures(
    mock_db_session,
    stage: str,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(id=uuid4(), canonical_summary="summary")
    pipeline = _pipeline(mock_db_session)
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=True, merged=False)
    )
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(503, request=request)

    if stage == "embedding":
        pipeline.embedding_service.embed_texts = AsyncMock(side_effect=TimeoutError("embedding"))
    elif stage == "clustering":
        item.embedding = [0.1]
        pipeline.event_clusterer.cluster_item = AsyncMock(side_effect=ConnectionError("clustering"))
    else:
        item.embedding = [0.1]
        pipeline.tier2_classifier.classify_event = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "provider unavailable", request=request, response=response
            )
        )

    with pytest.raises(RetryablePipelineError, match="post_tier1"):
        await pipeline._process_after_tier1(
            prepared=prepared,
            tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
            trends=[_trend()],
        )

    assert item.processing_status == ProcessingStatus.PENDING
    assert item.processing_started_at is None
    assert item.error_message is None


@pytest.mark.asyncio
async def test_process_items_can_retry_after_transient_failure_without_error_state(
    mock_db_session,
) -> None:
    item = _item()
    event = Event(id=uuid4(), canonical_summary="Seed summary")
    dedup = SimpleNamespace(
        find_duplicate=AsyncMock(return_value=SimpleNamespace(is_duplicate=False))
    )
    embedding = SimpleNamespace(
        embed_texts=AsyncMock(side_effect=[TimeoutError("temporary"), ([[0.1, 0.2]], 0, 1)])
    )
    clusterer = SimpleNamespace(
        cluster_item=AsyncMock(
            return_value=ClusterResult(
                item_id=item.id, event_id=event.id, created=True, merged=False
            )
        )
    )
    tier1 = SimpleNamespace(
        classify_items=AsyncMock(
            return_value=(
                [Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True)],
                Tier1Usage(api_calls=1),
            )
        )
    )
    tier2 = SimpleNamespace(
        classify_event=AsyncMock(
            return_value=(
                Tier2EventResult(event_id=event.id, categories_count=0, trend_impacts_count=0),
                Tier2Usage(api_calls=1),
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

    with pytest.raises(RetryablePipelineError):
        await pipeline.process_items([item], trends=[_trend()])

    assert item.processing_status == ProcessingStatus.PENDING
    assert item.error_message is None

    result = await pipeline.process_items([item], trends=[_trend()])

    assert result.classified == 1
    assert result.errors == 0
    assert item.processing_status == ProcessingStatus.CLASSIFIED
