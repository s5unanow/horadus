from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.processing.novelty_lane import (
    NoveltyLaneService,
    _item_summary,
    _merged_details,
    _normalized_text,
)
from src.processing.tier1_classifier import Tier1ItemResult, TrendRelevanceScore
from src.storage.models import Event, RawItem
from src.storage.novelty_models import NoveltyCandidate

pytestmark = pytest.mark.unit


def _tier1_result(*, item_id, max_relevance: int) -> Tier1ItemResult:
    return Tier1ItemResult(
        item_id=item_id,
        max_relevance=max_relevance,
        should_queue_tier2=max_relevance >= 5,
        trend_scores=[
            TrendRelevanceScore(
                trend_id="eu-russia",
                relevance_score=max_relevance,
                rationale="near threshold",
            )
        ],
    )


@pytest.mark.asyncio
async def test_capture_tier1_near_miss_persists_candidate(mock_db_session) -> None:
    item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="item-1",
        title="Border logistics activity rises",
        url="https://example.test/item-1",
        raw_content="Convoys and checkpoints increased near the crossing.",
        content_hash="hash-1",
    )
    service = NoveltyLaneService(session=mock_db_session)
    mock_db_session.scalar.side_effect = [None, 0]

    await service.capture_tier1_near_miss(
        item=item,
        tier1_result=_tier1_result(item_id=item.id, max_relevance=4),
    )

    candidate = mock_db_session.add.call_args.args[0]
    assert isinstance(candidate, NoveltyCandidate)
    assert candidate.candidate_kind == "near_threshold_item"
    assert candidate.raw_item_id == item.id
    assert candidate.near_threshold_hits == 1
    assert candidate.last_tier1_max_relevance == 4
    assert candidate.details["reason"] == "near_threshold_item"
    assert candidate.details["top_trend_scores"][0]["trend_id"] == "eu-russia"


@pytest.mark.asyncio
async def test_capture_tier1_near_miss_ignores_low_relevance(mock_db_session) -> None:
    item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="item-2",
        title="Low-signal chatter",
        raw_content="Routine commentary with little relevance.",
        content_hash="hash-2",
    )
    service = NoveltyLaneService(session=mock_db_session)

    await service.capture_tier1_near_miss(
        item=item,
        tier1_result=_tier1_result(item_id=item.id, max_relevance=2),
    )

    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_capture_tier1_near_miss_skips_queued_and_blank_summary(mock_db_session) -> None:
    item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="item-queued",
        title="Queued item",
        raw_content="Queued item content",
        content_hash="hash-queued",
    )
    blank_item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="item-blank",
        title=" ",
        raw_content=" ",
        content_hash="hash-blank",
    )
    service = NoveltyLaneService(session=mock_db_session)

    await service.capture_tier1_near_miss(
        item=item,
        tier1_result=Tier1ItemResult(item_id=item.id, max_relevance=5, should_queue_tier2=True),
    )
    await service.capture_tier1_near_miss(
        item=blank_item,
        tier1_result=_tier1_result(item_id=blank_item.id, max_relevance=4),
    )

    mock_db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_capture_event_candidate_updates_existing_candidate(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(tz=UTC)
    existing = NoveltyCandidate(
        id=uuid4(),
        cluster_key="existing-key",
        candidate_kind="event_gap",
        summary="Existing novelty cluster",
        details={"reason": "event_gap"},
        recurrence_count=1,
        distinct_source_count=1,
        actor_location_hits=0,
        near_threshold_hits=0,
        unmapped_signal_count=0,
        last_tier1_max_relevance=4,
        ranking_score=1.0,
        first_seen_at=now,
        last_seen_at=now,
    )
    event = Event(
        id=uuid4(),
        canonical_summary="Unmapped cross-border logistics signal",
        extracted_who=["Actor A", "Actor B"],
        extracted_what="Convoys repositioned near the crossing",
        extracted_where="Border Crossing",
        source_count=3,
        unique_source_count=2,
        extracted_claims={
            "_trend_impact_mapping": {
                "unresolved": [
                    {"reason": "no_matching_indicator"},
                    {"reason": "ambiguous_mapping"},
                ]
            }
        },
    )
    item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="item-3",
        raw_content="Convoys repositioned near the crossing.",
        content_hash="hash-3",
    )
    service = NoveltyLaneService(session=mock_db_session)
    mock_db_session.scalar.side_effect = [existing, 1]

    from src.processing import novelty_lane as novelty_lane_module

    monkeypatch.setattr(novelty_lane_module, "_cluster_key", lambda *_parts: "existing-key")
    await service.capture_event_candidate(
        event=event,
        item=item,
        tier1_result=_tier1_result(item_id=item.id, max_relevance=4),
        trend_impacts_seen=0,
        trend_updates=0,
    )

    assert existing.event_id == event.id
    assert existing.raw_item_id == item.id
    assert existing.recurrence_count == 2
    assert existing.distinct_source_count == 2
    assert existing.actor_location_hits == 1
    assert existing.near_threshold_hits == 1
    assert existing.unmapped_signal_count == 2
    assert existing.ranking_score > 1.0
    assert existing.details["unresolved_mapping_count"] == 2
    mock_db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_capture_event_candidate_skips_missing_id_and_blank_summary(
    mock_db_session,
) -> None:
    service = NoveltyLaneService(session=mock_db_session)
    item = RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id="item-4",
        raw_content="content",
        content_hash="hash-4",
    )

    await service.capture_event_candidate(
        event=Event(id=None, canonical_summary="No id"),
        item=item,
        tier1_result=_tier1_result(item_id=item.id, max_relevance=4),
        trend_impacts_seen=0,
        trend_updates=0,
    )
    await service.capture_event_candidate(
        event=Event(id=uuid4(), canonical_summary=" "),
        item=item,
        tier1_result=_tier1_result(item_id=item.id, max_relevance=4),
        trend_impacts_seen=0,
        trend_updates=0,
    )

    mock_db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_prune_lane_removes_low_ranked_candidates(mock_db_session, monkeypatch) -> None:
    service = NoveltyLaneService(session=mock_db_session)
    keep_id = uuid4()
    monkeypatch.setattr("src.processing.novelty_lane._MAX_LANE_CANDIDATES", 1)
    mock_db_session.scalar.return_value = 2
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [keep_id])

    await service._prune_lane()

    mock_db_session.execute.assert_awaited_once()
    mock_db_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_prune_lane_returns_when_keep_set_is_empty(mock_db_session, monkeypatch) -> None:
    service = NoveltyLaneService(session=mock_db_session)
    monkeypatch.setattr("src.processing.novelty_lane._MAX_LANE_CANDIDATES", 1)
    mock_db_session.scalar.return_value = 2
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    await service._prune_lane()

    mock_db_session.execute.assert_not_awaited()


def test_novelty_lane_helper_functions_cover_remaining_paths() -> None:
    long_item = RawItem(
        title=None,
        raw_content="word " * 80,
        source_id=uuid4(),
        external_id="helper-item",
        content_hash="helper-hash",
    )

    summary = _item_summary(long_item)

    assert summary.endswith("...")
    assert len(summary) <= 240
    assert _normalized_text(None) == ""
    assert _merged_details({"a": 1}, {"b": None, "c": 2}) == {"a": 1, "c": 2}
