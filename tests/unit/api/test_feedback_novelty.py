from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.api.routes.feedback import list_novelty_queue
from src.storage.models import NoveltyCandidate

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_list_novelty_queue_returns_serialized_candidates(mock_db_session) -> None:
    now = datetime.now(tz=UTC)
    candidate = NoveltyCandidate(
        id=uuid4(),
        cluster_key="cluster-a",
        candidate_kind="event_gap",
        summary="Unmapped logistics cluster",
        details={"reason": "unmapped_event"},
        recurrence_count=3,
        distinct_source_count=2,
        actor_location_hits=1,
        near_threshold_hits=1,
        unmapped_signal_count=2,
        last_tier1_max_relevance=4,
        ranking_score=4.25,
        first_seen_at=now,
        last_seen_at=now,
        event_id=uuid4(),
        raw_item_id=uuid4(),
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [candidate])

    result = await list_novelty_queue(
        days=14,
        limit=20,
        candidate_kind=None,
        session=mock_db_session,
    )

    assert len(result) == 1
    assert result[0].cluster_key == "cluster-a"
    assert result[0].candidate_kind == "event_gap"
    assert result[0].ranking_score == pytest.approx(4.25)
    assert result[0].details["reason"] == "unmapped_event"


@pytest.mark.asyncio
async def test_list_novelty_queue_applies_kind_filter(mock_db_session) -> None:
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    result = await list_novelty_queue(
        days=7,
        limit=10,
        candidate_kind="near_threshold_item",
        session=mock_db_session,
    )

    assert result == []
    executed_query = str(mock_db_session.scalars.await_args.args[0]).lower()
    assert "candidate_kind" in executed_query
