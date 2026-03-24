from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.processing.pipeline_orchestrator as orchestrator_module
from src.processing.event_clusterer import ClusterResult
from src.processing.pipeline_types import _PreparedItem
from src.processing.tier1_classifier import Tier1ItemResult
from src.processing.tier2_classifier import Tier2DeferredSemanticCacheWrite, Tier2Usage
from src.storage.models import Event
from tests.unit.processing.test_pipeline_orchestrator_additional import _item, _pipeline, _trend

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_process_after_tier1_restores_canonical_fields_when_degraded_hold_demotes_output(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(
        id=uuid4(),
        canonical_summary="primary title",
        event_summary="Stable canonical summary",
        extracted_what="Canonical extraction",
        categories=["military"],
        extraction_provenance={"stage": "tier2", "active_route": {"model": "gpt-4.1-mini"}},
        extraction_status="canonical",
    )
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=True,
                availability_degraded=True,
                quality_degraded=False,
                degraded_since_epoch=1,
                window=SimpleNamespace(total_calls=2, secondary_calls=1, failover_ratio=0.5),
            )
        ),
    )

    async def _classify_event(*, event: Event, trends: list[object]) -> tuple[object, Tier2Usage]:
        _ = trends
        event.event_summary = "Held degraded summary"
        event.extracted_what = "Held degraded extraction"
        event.categories = ["security"]
        event.extracted_claims = {"trend_impacts": [{"trend_id": "eu-russia"}]}
        event.extraction_provenance = {"stage": "tier2", "active_route": {"model": "gpt-4.1-nano"}}
        return (SimpleNamespace(event_id=event.id), Tier2Usage(api_calls=1, active_model="gpt"))

    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=SimpleNamespace(classify_event=AsyncMock(side_effect=_classify_event)),
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._maybe_enqueue_replay = AsyncMock(return_value=True)
    pipeline._capture_unresolved_trend_mapping = AsyncMock()
    pipeline._apply_trend_impacts = AsyncMock(return_value=(5, 0))
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=False, merged=True)
    )
    sync_claims = AsyncMock()
    deactivate_claims = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )
    monkeypatch.setattr(orchestrator_module, "sync_event_claims", sync_claims)
    monkeypatch.setattr(orchestrator_module, "deactivate_event_claims", deactivate_claims)

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )

    assert execution.result.degraded_llm_hold is True
    assert event.event_summary == "Stable canonical summary"
    assert event.extracted_what == "Canonical extraction"
    assert event.categories == ["military"]
    assert event.extraction_status == "provisional"
    assert event.provisional_extraction["summary"] == "Held degraded summary"
    assert event.provisional_extraction["replay_enqueued"] is True
    pipeline._capture_unresolved_trend_mapping.assert_not_awaited()
    sync_claims.assert_awaited_once_with(session=mock_db_session, event=event)
    deactivate_claims.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_after_tier1_deactivates_claim_rows_when_degraded_hold_has_no_canonical_claims(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(
        id=uuid4(),
        canonical_summary="primary title",
        extraction_status="none",
    )
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=True,
                availability_degraded=True,
                quality_degraded=False,
                degraded_since_epoch=1,
                window=SimpleNamespace(total_calls=2, secondary_calls=1, failover_ratio=0.5),
            )
        ),
    )

    async def _classify_event(*, event: Event, trends: list[object]) -> tuple[object, Tier2Usage]:
        _ = trends
        event.event_summary = "Held degraded summary"
        event.extracted_what = "Held degraded extraction"
        event.extracted_claims = {"trend_impacts": [{"trend_id": "eu-russia"}]}
        return (SimpleNamespace(event_id=event.id), Tier2Usage(api_calls=1, active_model="gpt"))

    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=SimpleNamespace(classify_event=AsyncMock(side_effect=_classify_event)),
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._maybe_enqueue_replay = AsyncMock(return_value=False)
    pipeline._apply_trend_impacts = AsyncMock(return_value=(5, 0))
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=False, merged=True)
    )
    sync_claims = AsyncMock()
    deactivate_claims = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )
    monkeypatch.setattr(orchestrator_module, "sync_event_claims", sync_claims)
    monkeypatch.setattr(orchestrator_module, "deactivate_event_claims", deactivate_claims)

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )

    assert execution.result.degraded_llm_hold is True
    assert event.extraction_status == "provisional"
    assert event.provisional_extraction["summary"] == "Held degraded summary"
    deactivate_claims.assert_awaited_once_with(session=mock_db_session, event_id=event.id)
    sync_claims.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_after_tier1_treats_seeded_event_summary_as_noncanonical_on_first_hold(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(
        id=uuid4(),
        canonical_summary="primary title",
        event_summary="primary title",
        extraction_status="none",
    )
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=True,
                availability_degraded=True,
                quality_degraded=False,
                degraded_since_epoch=1,
                window=SimpleNamespace(total_calls=2, secondary_calls=1, failover_ratio=0.5),
            )
        ),
    )

    async def _classify_event(*, event: Event, trends: list[object]) -> tuple[object, Tier2Usage]:
        _ = trends
        event.event_summary = "Held degraded summary"
        event.extracted_what = "Held degraded extraction"
        event.extracted_claims = {"trend_impacts": [{"trend_id": "eu-russia"}]}
        return (SimpleNamespace(event_id=event.id), Tier2Usage(api_calls=1, active_model="gpt"))

    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=SimpleNamespace(classify_event=AsyncMock(side_effect=_classify_event)),
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._maybe_enqueue_replay = AsyncMock(return_value=False)
    pipeline._apply_trend_impacts = AsyncMock(return_value=(5, 0))
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=False, merged=True)
    )
    sync_claims = AsyncMock()
    deactivate_claims = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )
    monkeypatch.setattr(orchestrator_module, "sync_event_claims", sync_claims)
    monkeypatch.setattr(orchestrator_module, "deactivate_event_claims", deactivate_claims)

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )

    assert execution.result.degraded_llm_hold is True
    assert event.extraction_status == "provisional"
    assert event.provisional_extraction["summary"] == "Held degraded summary"
    deactivate_claims.assert_awaited_once_with(session=mock_db_session, event_id=event.id)
    sync_claims.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_after_tier1_preserves_canonical_claims_on_repeat_degraded_hold(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(
        id=uuid4(),
        canonical_summary="primary title",
        event_summary="Stable canonical summary",
        extracted_what="Canonical extraction",
        extracted_claims={"claims": ["Canonical statement"]},
        extraction_provenance={"stage": "tier2", "active_route": {"model": "gpt-4.1-mini"}},
        extraction_status="provisional",
        provisional_extraction={"summary": "Earlier held degraded summary"},
    )
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=True,
                availability_degraded=True,
                quality_degraded=False,
                degraded_since_epoch=1,
                window=SimpleNamespace(total_calls=3, secondary_calls=2, failover_ratio=0.67),
            )
        ),
    )

    async def _classify_event(*, event: Event, trends: list[object]) -> tuple[object, Tier2Usage]:
        _ = trends
        event.event_summary = "New held degraded summary"
        event.extracted_what = "New held degraded extraction"
        event.extracted_claims = {"claims": ["New degraded statement"]}
        return (SimpleNamespace(event_id=event.id), Tier2Usage(api_calls=1, active_model="gpt"))

    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=SimpleNamespace(classify_event=AsyncMock(side_effect=_classify_event)),
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._maybe_enqueue_replay = AsyncMock(return_value=True)
    pipeline._apply_trend_impacts = AsyncMock(return_value=(5, 0))
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=False, merged=True)
    )
    sync_claims = AsyncMock()
    deactivate_claims = AsyncMock()
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )
    monkeypatch.setattr(orchestrator_module, "sync_event_claims", sync_claims)
    monkeypatch.setattr(orchestrator_module, "deactivate_event_claims", deactivate_claims)

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )

    assert execution.result.degraded_llm_hold is True
    assert event.event_summary == "Stable canonical summary"
    assert event.extracted_claims == {"claims": ["Canonical statement"]}
    assert event.extraction_status == "provisional"
    assert event.provisional_extraction["summary"] == "New held degraded summary"
    sync_claims.assert_awaited_once_with(session=mock_db_session, event=event)
    deactivate_claims.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_after_tier1_reports_zero_impacts_when_degraded_payload_is_not_a_list(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(
        id=uuid4(),
        canonical_summary="summary",
        extracted_claims={"trend_impacts": "bad"},
    )
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=True,
                availability_degraded=True,
                quality_degraded=False,
                degraded_since_epoch=1,
                window=SimpleNamespace(total_calls=2, secondary_calls=1, failover_ratio=0.5),
            )
        ),
    )
    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=SimpleNamespace(
            classify_event=AsyncMock(
                return_value=(SimpleNamespace(event_id=event.id), Tier2Usage(api_calls=1))
            )
        ),
    )
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=True, merged=False)
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._maybe_enqueue_replay = AsyncMock(return_value=False)
    pipeline._apply_trend_impacts = AsyncMock(return_value=(9, 9))
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )

    assert execution.result.trend_impacts_seen == 0


@pytest.mark.asyncio
async def test_process_after_tier1_persists_deferred_cache_write_only_after_canonical_outcome(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(id=uuid4(), canonical_summary="summary")
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=False,
                availability_degraded=False,
                quality_degraded=False,
                degraded_since_epoch=None,
                window=SimpleNamespace(total_calls=2, secondary_calls=0, failover_ratio=0.0),
            )
        ),
    )
    deferred_write = Tier2DeferredSemanticCacheWrite(
        provider="openai",
        model="gpt-4.1-mini",
        reasoning_effort="medium",
        payload={"event_id": str(event.id)},
        value='{"summary":"summary"}',
    )
    captured: dict[str, object] = {}

    class _Tier2:
        def __init__(self) -> None:
            self.persist_deferred_semantic_cache_write = AsyncMock()

        async def classify_event(
            self,
            *,
            event: Event,
            trends: list[object],
            defer_semantic_cache_write: bool,
        ) -> tuple[object, Tier2Usage]:
            _ = trends
            captured["defer_semantic_cache_write"] = defer_semantic_cache_write
            event.extracted_claims = {"trend_impacts": [{"trend_id": "eu-russia"}]}
            return (
                SimpleNamespace(event_id=event.id),
                Tier2Usage(
                    api_calls=1,
                    active_model="gpt",
                    deferred_semantic_cache_write=deferred_write,
                ),
            )

    tier2 = _Tier2()
    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=tier2,
    )
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=True, merged=False)
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._capture_unresolved_trend_mapping = AsyncMock()
    pipeline._apply_trend_impacts = AsyncMock(return_value=(1, 1))
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )

    assert execution.result.degraded_llm_hold is False
    assert captured["defer_semantic_cache_write"] is True
    tier2.persist_deferred_semantic_cache_write.assert_awaited_once_with(write=deferred_write)


@pytest.mark.asyncio
async def test_process_after_tier1_skips_deferred_cache_write_when_degraded_hold_keeps_output_provisional(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(id=uuid4(), canonical_summary="summary")
    tracker = SimpleNamespace(
        record_invocation=MagicMock(),
        evaluate=MagicMock(
            return_value=SimpleNamespace(
                stage="tier2",
                is_degraded=True,
                availability_degraded=True,
                quality_degraded=False,
                degraded_since_epoch=1,
                window=SimpleNamespace(total_calls=2, secondary_calls=1, failover_ratio=0.5),
            )
        ),
    )
    deferred_write = Tier2DeferredSemanticCacheWrite(
        provider="openai",
        model="gpt-4.1-nano",
        reasoning_effort="low",
        payload={"event_id": str(event.id)},
        value='{"summary":"held"}',
    )
    captured: dict[str, object] = {}

    class _Tier2:
        def __init__(self) -> None:
            self.persist_deferred_semantic_cache_write = AsyncMock()

        async def classify_event(
            self,
            *,
            event: Event,
            trends: list[object],
            defer_semantic_cache_write: bool,
        ) -> tuple[object, Tier2Usage]:
            _ = trends
            captured["defer_semantic_cache_write"] = defer_semantic_cache_write
            event.event_summary = "Held degraded summary"
            event.extracted_what = "Held degraded extraction"
            event.extracted_claims = {"trend_impacts": [{"trend_id": "eu-russia"}]}
            return (
                SimpleNamespace(event_id=event.id),
                Tier2Usage(
                    api_calls=1,
                    active_model="gpt",
                    deferred_semantic_cache_write=deferred_write,
                ),
            )

    tier2 = _Tier2()
    pipeline = _pipeline(
        mock_db_session,
        degraded_llm_tracker=tracker,
        tier2_classifier=tier2,
    )
    pipeline.event_clusterer.cluster_item = AsyncMock(
        return_value=ClusterResult(item_id=item.id, event_id=event.id, created=True, merged=False)
    )
    pipeline._load_event = AsyncMock(return_value=event)
    pipeline._maybe_enqueue_replay = AsyncMock(return_value=True)
    pipeline._capture_unresolved_trend_mapping = AsyncMock()
    pipeline._apply_trend_impacts = AsyncMock(return_value=(9, 9))
    monkeypatch.setattr(orchestrator_module, "set_llm_degraded_mode", lambda **_: None)
    monkeypatch.setattr(
        orchestrator_module, "record_processing_tier2_language_usage", lambda **_: None
    )

    execution = await pipeline._process_after_tier1(
        prepared=prepared,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=8, should_queue_tier2=True),
        trends=[_trend()],
    )

    assert execution.result.degraded_llm_hold is True
    assert captured["defer_semantic_cache_write"] is True
    tier2.persist_deferred_semantic_cache_write.assert_not_awaited()
