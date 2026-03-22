from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

import src.api.routes.events as events_module
from src.api.routes.events import (
    EventMergeRequest,
    EventRepairResponse,
    EventSplitRequest,
    get_event,
    list_events,
    merge_event,
    split_event_route,
)
from src.storage.models import Event

pytestmark = pytest.mark.unit


def _build_event(
    *,
    event_id: UUID | None = None,
    lifecycle_status: str = "confirmed",
    has_contradictions: bool = False,
    contradiction_notes: str | None = None,
    event_summary: str | None = None,
) -> Event:
    now = datetime.now(tz=UTC)
    return Event(
        id=event_id or uuid4(),
        canonical_summary="Cross-border force movements reported",
        event_summary=event_summary,
        categories=["military"],
        source_count=4,
        unique_source_count=3,
        independent_evidence_count=2,
        corroboration_score=1.35,
        corroboration_mode="provenance_aware",
        provenance_summary={
            "method": "provenance_aware",
            "independent_evidence_count": 2,
            "cluster_health": {
                "cluster_cohesion_score": 1.0,
                "split_risk_score": 0.0,
            },
        },
        lifecycle_status=lifecycle_status,
        has_contradictions=has_contradictions,
        contradiction_notes=contradiction_notes,
        first_seen_at=now - timedelta(hours=6),
        last_mention_at=now,
        extracted_who=["Country A", "Country B"],
        extracted_what="Military units repositioned",
        extracted_where="Border region",
    )


def _assert_event_detail_summary(result, *, event: Event) -> None:
    assert result.id == event.id
    assert result.epistemic_state == "contested"
    assert result.activity_state == "active"
    assert result.independent_evidence_count == 2
    assert result.corroboration_mode == "provenance_aware"
    assert result.corroboration_score == pytest.approx(1.35)
    assert result.provenance_summary["method"] == "provenance_aware"
    assert result.has_contradictions is True
    assert "conflict" in (result.contradiction_notes or "").lower()
    assert result.lineage[0]["lineage_kind"] == "merge"
    assert result.cluster_cohesion_score == pytest.approx(1.0)
    assert result.split_risk_score == pytest.approx(0.0)


def _assert_event_detail_relations(result, *, mock_db_session) -> None:
    assert len(result.sources) == 2
    assert result.sources[0]["source_name"] == "Reuters"
    assert len(result.claims) == 2
    assert result.claims[0]["claim_key"] == "__event__"
    assert result.claims[1]["is_active"] is False
    assert len(result.trend_impacts) == 2
    assert "event_claim_id" in result.trend_impacts[0]
    assert result.trend_impacts[0]["claim_text"] == "Troops advanced into border region"
    assert result.trend_impacts[0]["direction"] == "escalatory"
    assert result.trend_impacts[1]["direction"] == "de_escalatory"
    claim_query_text = str(mock_db_session.execute.await_args_list[2].args[0]).lower()
    assert "event_claims.is_active is true" in claim_query_text
    assert "event_claims.id in" in claim_query_text


@pytest.mark.asyncio
async def test_list_events_returns_filtered_payload(mock_db_session) -> None:
    event = _build_event(lifecycle_status="confirmed")
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [event])

    result = await list_events(
        lifecycle="confirmed",
        contradicted=False,
        category="military",
        trend_id=uuid4(),
        days=7,
        limit=20,
        session=mock_db_session,
    )

    assert len(result) == 1
    assert result[0].id == event.id
    assert result[0].epistemic_state == "confirmed"
    assert result[0].activity_state == "active"
    assert result[0].lifecycle_status == "confirmed"
    assert result[0].unique_source_count == 3
    assert result[0].independent_evidence_count == 2
    assert result[0].corroboration_mode == "provenance_aware"
    assert result[0].summary == event.canonical_summary
    assert result[0].cluster_cohesion_score == pytest.approx(1.0)
    assert result[0].split_risk_score == pytest.approx(0.0)
    query = mock_db_session.scalars.await_args.args[0]
    query_text = str(query)
    query_text_lower = query_text.lower()
    assert "events.lifecycle_status" in query_text
    assert "events.has_contradictions" in query_text
    assert "exists" in query_text_lower
    assert "trend_evidence.trend_id" in query_text
    assert "trend_evidence.is_invalidated is false" in query_text_lower
    assert "join trend_evidence" not in query_text_lower


@pytest.mark.asyncio
async def test_list_events_prefers_event_summary_when_present(mock_db_session) -> None:
    event = _build_event(event_summary="Synthesized cross-border event summary")
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [event])

    result = await list_events(days=7, limit=5, session=mock_db_session)

    assert result[0].summary == "Synthesized cross-border event summary"


@pytest.mark.asyncio
async def test_list_events_applies_epistemic_and_activity_filters(mock_db_session) -> None:
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    await list_events(
        epistemic="contested",
        activity="dormant",
        days=7,
        limit=10,
        session=mock_db_session,
    )

    query_text = str(mock_db_session.scalars.await_args.args[0]).lower()
    assert "events.epistemic_state" in query_text
    assert "events.activity_state" in query_text


@pytest.mark.asyncio
async def test_list_events_allows_unfiltered_queries(mock_db_session) -> None:
    event = _build_event()
    event.categories = None
    event.extracted_who = None
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [event])

    result = await list_events(
        lifecycle=None,
        contradicted=None,
        category=None,
        trend_id=None,
        days=3,
        limit=5,
        session=mock_db_session,
    )

    assert len(result) == 1
    assert result[0].epistemic_state == "confirmed"
    assert result[0].categories == []
    assert result[0].extracted_who is None
    query_text = str(mock_db_session.scalars.await_args.args[0]).lower()
    where_clause = query_text.split("where", 1)[1]
    assert "events.lifecycle_status =" not in where_clause
    assert "events.has_contradictions is" not in where_clause
    assert "array_position" not in query_text
    assert "trend_evidence.trend_id" not in query_text


@pytest.mark.asyncio
async def test_list_events_excludes_closed_zero_source_stubs(mock_db_session) -> None:
    mock_db_session.scalars.return_value = SimpleNamespace(all=list)

    await list_events(days=7, limit=10, session=mock_db_session)

    query_text = str(mock_db_session.scalars.await_args.args[0]).lower()
    assert "events.activity_state = :activity_state_1" in query_text
    assert "events.source_count = :source_count_1" in query_text


@pytest.mark.asyncio
async def test_get_event_returns_404_when_missing(mock_db_session) -> None:
    mock_db_session.get.return_value = None

    with pytest.raises(HTTPException, match="not found") as exc:
        await get_event(event_id=uuid4(), session=mock_db_session)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_event_returns_detail_with_sources_and_impacts(
    mock_db_session,
    monkeypatch,
) -> None:
    event = _build_event(
        has_contradictions=True,
        contradiction_notes="Source narratives conflict on withdrawal timeline.",
    )
    mock_db_session.get.return_value = event
    impacted_claim_id = uuid4()
    responses = iter(
        [
            [
                ("Reuters", "https://example.com/a1"),
                ("BBC", "https://example.com/a2"),
            ],
            [
                (
                    uuid4(),
                    impacted_claim_id,
                    "Troops advanced into border region",
                    "military_movement",
                    0.12,
                ),
                (uuid4(), uuid4(), "Negotiators resumed talks", "diplomatic_talks", -0.05),
            ],
            [
                (uuid4(), "__event__", "Cluster summary", "fallback", True),
                (
                    impacted_claim_id,
                    "troops advanced into border region",
                    "Troops advanced into border region",
                    "statement",
                    False,
                ),
            ],
        ]
    )

    async def _execute(_query):
        return SimpleNamespace(all=lambda: next(responses))

    mock_db_session.execute.side_effect = _execute
    monkeypatch.setattr(
        events_module,
        "load_event_lineage",
        AsyncMock(
            return_value=[
                {
                    "lineage_kind": "merge",
                    "role": "target",
                    "counterpart_event_id": uuid4(),
                    "moved_item_count": 2,
                }
            ]
        ),
    )

    result = await get_event(event_id=event.id, session=mock_db_session)

    _assert_event_detail_summary(result, event=event)
    _assert_event_detail_relations(result, mock_db_session=mock_db_session)


@pytest.mark.asyncio
async def test_get_event_computes_missing_cluster_health_without_mutating_event(
    mock_db_session,
    monkeypatch,
) -> None:
    event = _build_event()
    event.provenance_summary = {"method": "provenance_aware"}
    mock_db_session.get.return_value = event
    responses = iter([[], [], []])

    async def _execute(_query):
        return SimpleNamespace(all=lambda: next(responses))

    mock_db_session.execute.side_effect = _execute
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [[1.0, 0.0], [0.0, 1.0]]),
    ]
    monkeypatch.setattr(events_module, "load_event_lineage", AsyncMock(return_value=[]))

    result = await get_event(event_id=event.id, session=mock_db_session)

    assert result.cluster_cohesion_score == pytest.approx(0.0)
    assert result.split_risk_score == pytest.approx(1.0)
    assert event.provenance_summary == {"method": "provenance_aware"}


@pytest.mark.asyncio
async def test_get_event_keeps_claims_visible_during_lineage_replay_pending(
    mock_db_session,
    monkeypatch,
) -> None:
    event = _build_event()
    event.extraction_provenance = {
        "status": "replay_pending",
        "reason": "event_lineage_repair",
    }
    mock_db_session.get.return_value = event
    claim_id = uuid4()
    responses = iter(
        [
            [],
            [],
            [
                (
                    claim_id,
                    "__event__",
                    "Claim before replay",
                    "fallback",
                    False,
                )
            ],
        ]
    )

    async def _execute(_query):
        return SimpleNamespace(all=lambda: next(responses))

    mock_db_session.execute.side_effect = _execute
    monkeypatch.setattr(events_module, "load_event_lineage", AsyncMock(return_value=[]))

    result = await get_event(event_id=event.id, session=mock_db_session)

    assert len(result.claims) == 1
    assert result.claims[0]["claim_text"] == "Claim before replay"
    claim_query_text = str(mock_db_session.execute.await_args_list[1].args[0]).lower()
    assert "event_claims.is_active is true" not in claim_query_text


@pytest.mark.asyncio
async def test_event_responses_use_resolved_fallback_corroboration_values(
    mock_db_session,
    monkeypatch,
) -> None:
    fallback_event = _build_event()
    fallback_event.independent_evidence_count = 0
    fallback_event.corroboration_mode = ""
    fallback_event.corroboration_score = 0
    fallback_event.unique_source_count = 3
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [fallback_event])
    mock_db_session.get.return_value = fallback_event
    mock_db_session.execute.side_effect = [
        SimpleNamespace(all=list),
        SimpleNamespace(all=list),
        SimpleNamespace(all=list),
    ]
    monkeypatch.setattr(events_module, "load_event_lineage", AsyncMock(return_value=[]))

    list_result = await list_events(days=7, limit=10, session=mock_db_session)
    detail_result = await get_event(event_id=fallback_event.id, session=mock_db_session)

    assert list_result[0].independent_evidence_count == 3
    assert list_result[0].corroboration_mode == "fallback"
    assert detail_result.independent_evidence_count == 3
    assert detail_result.corroboration_mode == "fallback"
    assert detail_result.corroboration_score == pytest.approx(3.0)
    assert detail_result.lineage == []


@pytest.mark.asyncio
async def test_merge_event_route_validates_source_target_and_service_errors(
    mock_db_session,
    monkeypatch,
) -> None:
    source_event = _build_event()
    target_event = _build_event()
    payload = EventMergeRequest(target_event_id=target_event.id, notes="merge")

    mock_db_session.get.side_effect = [None]
    with pytest.raises(HTTPException, match="not found"):
        await merge_event(event_id=source_event.id, payload=payload, session=mock_db_session)

    mock_db_session.get.side_effect = [source_event, None]
    with pytest.raises(HTTPException, match="not found"):
        await merge_event(event_id=source_event.id, payload=payload, session=mock_db_session)

    monkeypatch.setattr(
        events_module, "merge_events", AsyncMock(side_effect=ValueError("bad merge"))
    )
    mock_db_session.get.side_effect = [source_event, target_event]
    with pytest.raises(HTTPException, match="bad merge"):
        await merge_event(event_id=source_event.id, payload=payload, session=mock_db_session)

    monkeypatch.setattr(events_module, "merge_events", AsyncMock(side_effect=RuntimeError("busy")))
    mock_db_session.get.side_effect = [source_event, target_event]
    with pytest.raises(HTTPException, match="busy") as exc_info:
        await merge_event(event_id=source_event.id, payload=payload, session=mock_db_session)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_merge_event_route_returns_service_payload(mock_db_session, monkeypatch) -> None:
    source_event = _build_event()
    target_event = _build_event()
    repair = EventRepairResponse(
        action="merge",
        lineage_id=uuid4(),
        source_event_id=source_event.id,
        target_event_id=target_event.id,
        created_event_id=None,
        moved_item_ids=[uuid4()],
        invalidated_evidence_ids=[uuid4()],
        replay_enqueued_event_ids=[target_event.id],
    )
    monkeypatch.setattr(
        events_module,
        "merge_events",
        AsyncMock(
            return_value=SimpleNamespace(
                action=repair.action,
                lineage_id=repair.lineage_id,
                source_event_id=repair.source_event_id,
                target_event_id=repair.target_event_id,
                created_event_id=repair.created_event_id,
                moved_item_ids=tuple(repair.moved_item_ids),
                invalidated_evidence_ids=tuple(repair.invalidated_evidence_ids),
                replay_enqueued_event_ids=tuple(repair.replay_enqueued_event_ids),
            )
        ),
    )
    mock_db_session.get.side_effect = [source_event, target_event]

    result = await merge_event(
        event_id=source_event.id,
        payload=EventMergeRequest(target_event_id=target_event.id),
        session=mock_db_session,
    )

    assert result.target_event_id == target_event.id
    mock_db_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_split_event_route_validates_source_and_service_errors(
    mock_db_session,
    monkeypatch,
) -> None:
    source_event = _build_event()
    payload = EventSplitRequest(item_ids=[uuid4()], notes="split")

    mock_db_session.get.side_effect = [None]
    with pytest.raises(HTTPException, match="not found"):
        await split_event_route(event_id=source_event.id, payload=payload, session=mock_db_session)

    monkeypatch.setattr(
        events_module, "split_event", AsyncMock(side_effect=ValueError("bad split"))
    )
    mock_db_session.get.side_effect = [source_event]
    with pytest.raises(HTTPException, match="bad split"):
        await split_event_route(event_id=source_event.id, payload=payload, session=mock_db_session)

    monkeypatch.setattr(events_module, "split_event", AsyncMock(side_effect=RuntimeError("busy")))
    mock_db_session.get.side_effect = [source_event]
    with pytest.raises(HTTPException, match="busy") as exc_info:
        await split_event_route(event_id=source_event.id, payload=payload, session=mock_db_session)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_split_event_route_returns_service_payload(mock_db_session, monkeypatch) -> None:
    source_event = _build_event()
    created_event_id = uuid4()
    monkeypatch.setattr(
        events_module,
        "split_event",
        AsyncMock(
            return_value=SimpleNamespace(
                action="split",
                lineage_id=uuid4(),
                source_event_id=source_event.id,
                target_event_id=created_event_id,
                created_event_id=created_event_id,
                moved_item_ids=(uuid4(),),
                invalidated_evidence_ids=(uuid4(),),
                replay_enqueued_event_ids=(source_event.id, created_event_id),
            )
        ),
    )
    mock_db_session.get.side_effect = [source_event]

    result = await split_event_route(
        event_id=source_event.id,
        payload=EventSplitRequest(item_ids=[uuid4()]),
        session=mock_db_session,
    )

    assert result.created_event_id == created_event_id
    mock_db_session.flush.assert_awaited()
