from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.processing.event_cluster_link import ClusterResult
from src.processing.pipeline_types import PipelineUsage, _PreparedItem
from src.processing.tier1_classifier import Tier1ItemResult
from src.processing.tier2_candidate_processor import stage_tier2_candidate
from src.processing.tier2_candidate_suppression import (
    resolve_processing_event_suppression,
    suppress_tier2_candidate,
)
from src.storage.event_state import EventActivityState, EventEpistemicState
from src.storage.models import Event, ProcessingStatus, RawItem

pytestmark = pytest.mark.unit


def _item() -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=str(uuid4()),
        raw_content="Terminal event candidate",
        content_hash="a" * 64,
        fetched_at=datetime.now(UTC),
        embedding=[0.1],
        embedding_model="test-model",
        processing_status=ProcessingStatus.PROCESSING,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("epistemic_state", "activity_state", "expected_action"),
    [
        (
            EventEpistemicState.RETRACTED.value,
            EventActivityState.ACTIVE.value,
            "terminal_retracted",
        ),
        (
            EventEpistemicState.CONFIRMED.value,
            EventActivityState.CLOSED.value,
            "terminal_closed",
        ),
    ],
)
async def test_resolve_suppression_prioritizes_terminal_split_state(
    epistemic_state: str,
    activity_state: str,
    expected_action: str,
) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Terminal event",
        epistemic_state=epistemic_state,
        activity_state=activity_state,
    )
    owner = SimpleNamespace(_event_suppression_action=AsyncMock())
    cluster_result = ClusterResult(
        item_id=uuid4(),
        event_id=event.id,
        created=False,
        merged=True,
    )

    action = await resolve_processing_event_suppression(
        owner=owner,
        event=event,
        cluster_result=cluster_result,
    )

    assert action == expected_action
    owner._event_suppression_action.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("feedback_action", "expected_action"),
    [("invalidate", "invalidate"), (object(), None)],
)
async def test_resolve_suppression_uses_feedback_for_active_event(
    feedback_action: object,
    expected_action: str | None,
) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Active event",
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.ACTIVE.value,
    )
    owner = SimpleNamespace(
        _event_suppression_action=AsyncMock(return_value=feedback_action),
    )
    cluster_result = ClusterResult(
        item_id=uuid4(),
        event_id=event.id,
        created=False,
        merged=True,
    )

    action = await resolve_processing_event_suppression(
        owner=owner,
        event=event,
        cluster_result=cluster_result,
    )

    assert action == expected_action
    owner._event_suppression_action.assert_awaited_once_with(event_id=event.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("terminal_closed", ProcessingStatus.CLASSIFIED),
        ("invalidate", ProcessingStatus.NOISE),
    ],
)
async def test_suppress_candidate_finishes_without_tier2(
    action: str,
    expected_status: ProcessingStatus,
) -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    cluster_result = ClusterResult(
        item_id=item.id,
        event_id=uuid4(),
        created=False,
        merged=True,
    )
    record_suppression = MagicMock()
    owner = SimpleNamespace(
        session=SimpleNamespace(flush=AsyncMock()),
        record_processing_event_suppression=record_suppression,
        _build_item_result=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    staged, execution = await suppress_tier2_candidate(
        owner=owner,
        prepared=prepared,
        cluster_result=cluster_result,
        embedded=True,
        usage=PipelineUsage(tier1_api_calls=1),
        action=action,
    )

    assert staged is None
    assert execution.result.status == expected_status
    assert execution.usage.tier1_api_calls == 1
    record_suppression.assert_called_once_with(
        action=action,
        stage="pipeline_post_cluster",
    )


@pytest.mark.asyncio
async def test_stage_tier2_candidate_suppresses_closed_event() -> None:
    item = _item()
    prepared = _PreparedItem(item=item, item_id=item.id, raw_content=item.raw_content)
    event = Event(
        id=uuid4(),
        canonical_summary="Closed concurrent winner",
        epistemic_state=EventEpistemicState.CONFIRMED.value,
        activity_state=EventActivityState.CLOSED.value,
    )
    cluster_result = ClusterResult(
        item_id=item.id,
        event_id=event.id,
        created=False,
        merged=True,
    )
    feedback_action = AsyncMock()
    owner = SimpleNamespace(
        session=SimpleNamespace(flush=AsyncMock()),
        event_clusterer=SimpleNamespace(cluster_item=AsyncMock(return_value=cluster_result)),
        _load_event=AsyncMock(return_value=event),
        _event_suppression_action=feedback_action,
        record_processing_event_suppression=MagicMock(),
        _build_item_result=lambda **kwargs: SimpleNamespace(**kwargs),
        _raise_retryable_failure_if_needed=lambda **_: None,
    )

    staged, execution = await stage_tier2_candidate(
        owner=owner,
        prepared=prepared,
        tier1_result=Tier1ItemResult(
            item_id=item.id,
            max_relevance=8,
            should_queue_tier2=True,
        ),
    )

    assert staged is None
    assert execution is not None
    assert execution.result.status == ProcessingStatus.CLASSIFIED
    feedback_action.assert_not_called()
