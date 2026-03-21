from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

import src.processing.event_lineage as event_lineage_module
import src.processing.event_lineage_replay as event_lineage_replay_module
from src.processing.event_lineage import (
    _build_canonical_summary,
    _build_event_from_rows,
    _close_empty_merged_event,
    _delete_event_replay_queue_items,
    _enqueue_event_replay,
    _EventItemRow,
    _invalidation_compensation_delta,
    _item_timestamp,
    _load_event_item_rows,
    _load_prior_compensation_by_evidence_id,
    _load_trends_for_evidence,
    _mark_event_claims_stale,
    _mark_event_replay_pending,
    _pick_primary_item,
    _refresh_event_after_item_change,
    _repair_affected_events,
    _require_event_id,
    load_event_lineage,
    merge_events,
    select_from_active_evidence,
    split_event,
)
from src.processing.event_lineage_replay import (
    clear_stale_event_extractions,
    mark_lineages_superseded_for_replay_requests,
    replay_source_provenance,
)
from src.storage.event_lineage_models import EventLineage
from src.storage.models import (
    Event,
    EventClaim,
    EventItem,
    RawItem,
    Trend,
    TrendEvidence,
)

pytestmark = pytest.mark.unit


def _build_item(*, title: str = "Item title") -> RawItem:
    return RawItem(
        id=uuid4(),
        source_id=uuid4(),
        external_id=f"raw-{uuid4()}",
        title=title,
        raw_content=f"{title} body",
        content_hash="a" * 64,
        published_at=datetime.now(tz=UTC),
    )


@pytest.mark.asyncio
async def test_split_event_validates_selected_items(mock_db_session) -> None:
    source_event = Event(id=uuid4(), canonical_summary="source")
    row = _EventItemRow(
        link=EventItem(event_id=source_event.id, item_id=uuid4()), item=_build_item()
    )
    other_row = _EventItemRow(
        link=EventItem(event_id=source_event.id, item_id=uuid4()), item=_build_item(title="Other")
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=[row, other_row])
    )

    with pytest.raises(ValueError, match="at least one current event item"):
        await split_event(
            session=mock_db_session,
            source_event=source_event,
            item_ids=[],
            notes=None,
            created_by=None,
        )

    with pytest.raises(ValueError, match="must all belong"):
        await split_event(
            session=mock_db_session,
            source_event=source_event,
            item_ids=[row.item.id, uuid4()],
            notes=None,
            created_by=None,
        )

    with pytest.raises(ValueError, match="leave at least one item"):
        await split_event(
            session=mock_db_session,
            source_event=source_event,
            item_ids=[row.item.id, other_row.item.id],
            notes=None,
            created_by=None,
        )
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_split_event_returns_repair_result(mock_db_session, monkeypatch) -> None:
    source_event = Event(id=uuid4(), canonical_summary="source")
    new_event = Event(id=uuid4(), canonical_summary="new")
    row = _EventItemRow(
        link=EventItem(event_id=source_event.id, item_id=uuid4()),
        item=_build_item(),
    )
    other_row = _EventItemRow(
        link=EventItem(event_id=source_event.id, item_id=uuid4()),
        item=_build_item(title="Other item"),
    )
    lineage_id = uuid4()
    added: list[object] = []

    def _add(obj: object) -> None:
        added.append(obj)

    async def _flush() -> None:
        if added and isinstance(added[-1], EventLineage):
            added[-1].id = lineage_id

    mock_db_session.add.side_effect = _add
    mock_db_session.flush.side_effect = _flush
    monkeypatch.setattr(
        event_lineage_module,
        "_load_event_item_rows",
        AsyncMock(return_value=[row, other_row]),
    )
    monkeypatch.setattr(
        event_lineage_module, "_build_event_from_rows", AsyncMock(return_value=new_event)
    )
    monkeypatch.setattr(event_lineage_module, "_refresh_event_after_item_change", AsyncMock())
    monkeypatch.setattr(
        event_lineage_module,
        "_repair_affected_events",
        AsyncMock(return_value=((uuid4(),), (source_event.id, new_event.id), (uuid4(), uuid4()))),
    )

    result = await split_event(
        session=mock_db_session,
        source_event=source_event,
        item_ids=[row.item.id],
        notes="split",
        created_by="analyst",
    )

    assert result.action == "split"
    assert result.lineage_id == lineage_id
    assert result.created_event_id == new_event.id
    assert row.link.event_id == new_event.id


@pytest.mark.asyncio
async def test_merge_events_validates_and_returns_result(mock_db_session, monkeypatch) -> None:
    source_event = Event(id=uuid4(), canonical_summary="source")
    target_event = Event(id=uuid4(), canonical_summary="target")
    merged_away_target = Event(
        id=uuid4(),
        canonical_summary="merged-away",
        source_count=0,
        activity_state="closed",
    )
    row = _EventItemRow(
        link=EventItem(event_id=source_event.id, item_id=uuid4()),
        item=_build_item(),
    )
    lineage_id = uuid4()
    added: list[object] = []

    def _add(obj: object) -> None:
        added.append(obj)

    async def _flush() -> None:
        if added and isinstance(added[-1], EventLineage):
            added[-1].id = lineage_id

    mock_db_session.add.side_effect = _add
    mock_db_session.flush.side_effect = _flush
    monkeypatch.setattr(
        event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=[row])
    )
    monkeypatch.setattr(event_lineage_module, "_refresh_event_after_item_change", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_close_empty_merged_event", AsyncMock())
    delete_replay_queue_items = AsyncMock()
    monkeypatch.setattr(
        event_lineage_module,
        "_delete_event_replay_queue_items",
        delete_replay_queue_items,
    )
    monkeypatch.setattr(event_lineage_module, "_mark_event_claims_stale", AsyncMock())
    monkeypatch.setattr(
        event_lineage_module,
        "_repair_affected_events",
        AsyncMock(return_value=((uuid4(),), (target_event.id,), (uuid4(),))),
    )

    with pytest.raises(ValueError, match="must differ"):
        await merge_events(
            session=mock_db_session,
            source_event=source_event,
            target_event=source_event,
            notes=None,
            created_by=None,
        )

    with pytest.raises(ValueError, match="empty closed stub"):
        await merge_events(
            session=mock_db_session,
            source_event=source_event,
            target_event=merged_away_target,
            notes=None,
            created_by=None,
        )

    result = await merge_events(
        session=mock_db_session,
        source_event=source_event,
        target_event=target_event,
        notes="merge",
        created_by="analyst",
    )

    assert result.action == "merge"
    assert result.lineage_id == lineage_id
    assert row.link.event_id == target_event.id
    delete_replay_queue_items.assert_awaited_once_with(
        session=mock_db_session,
        event_id=source_event.id,
    )


@pytest.mark.asyncio
async def test_merge_events_rejects_empty_source(mock_db_session, monkeypatch) -> None:
    source_event = Event(id=uuid4(), canonical_summary="source")
    target_event = Event(id=uuid4(), canonical_summary="target")
    monkeypatch.setattr(event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=[]))

    with pytest.raises(ValueError, match="has no linked items"):
        await merge_events(
            session=mock_db_session,
            source_event=source_event,
            target_event=target_event,
            notes=None,
            created_by=None,
        )


@pytest.mark.asyncio
async def test_load_event_lineage_formats_counterparts(mock_db_session) -> None:
    event_id = uuid4()
    counterpart = Event(id=uuid4(), canonical_summary="Counterpart summary")
    row = EventLineage(
        id=uuid4(),
        lineage_kind="merge",
        source_event_id=event_id,
        target_event_id=counterpart.id,
        details={"moved_item_count": 2, "status": "replay_pending"},
        created_by="analyst",
        notes="merge note",
        created_at=datetime.now(tz=UTC),
    )
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [row]),
        SimpleNamespace(all=lambda: [counterpart]),
    ]

    payload = await load_event_lineage(session=mock_db_session, event_id=event_id)

    assert payload[0]["role"] == "source"
    assert payload[0]["counterpart_summary"] == counterpart.canonical_summary


@pytest.mark.asyncio
async def test_load_event_item_rows_wraps_query_results(mock_db_session) -> None:
    link = EventItem(event_id=uuid4(), item_id=uuid4())
    item = _build_item()
    mock_db_session.execute.return_value = SimpleNamespace(all=lambda: [(link, item)])

    rows = await _load_event_item_rows(session=mock_db_session, event_id=uuid4())

    assert rows == [_EventItemRow(link=link, item=item)]
    query_text = str(mock_db_session.execute.await_args.args[0]).upper()
    assert "FOR UPDATE" in query_text


@pytest.mark.asyncio
async def test_build_event_from_rows_creates_event_and_cluster_health(
    mock_db_session, monkeypatch
) -> None:
    primary_item = _build_item(title="Primary")
    primary_item.embedding = [0.1, 0.2]
    primary_item.embedding_model = "text-embedding-3-large"
    primary_item.embedding_input_tokens = 128
    primary_item.embedding_retained_tokens = 96
    primary_item.embedding_was_truncated = True
    primary_item.embedding_truncation_strategy = "head"
    row = _EventItemRow(
        link=EventItem(event_id=uuid4(), item_id=primary_item.id), item=primary_item
    )
    mock_db_session.flush = AsyncMock()
    monkeypatch.setattr(
        event_lineage_module, "_pick_primary_item", AsyncMock(return_value=primary_item)
    )

    event = await _build_event_from_rows(session=mock_db_session, rows=[row])

    assert event.canonical_summary == "Primary"
    assert event.embedding == [0.1, 0.2]
    assert event.embedding_model == "text-embedding-3-large"
    assert event.embedding_input_tokens == 128
    assert event.embedding_retained_tokens == 96
    assert event.embedding_was_truncated is True
    assert event.embedding_truncation_strategy == "head"
    assert event.provenance_summary["cluster_health"]["cluster_cohesion_score"] == pytest.approx(
        1.0
    )


@pytest.mark.asyncio
async def test_refresh_event_after_item_change_handles_empty_rows(
    mock_db_session, monkeypatch
) -> None:
    event = Event(id=uuid4(), canonical_summary="event")
    close_empty = AsyncMock()
    monkeypatch.setattr(event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(event_lineage_module, "_close_empty_merged_event", close_empty)

    await _refresh_event_after_item_change(session=mock_db_session, event=event)

    close_empty.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_refresh_event_after_item_change_updates_rollup(mock_db_session, monkeypatch) -> None:
    item_one = _build_item(title="One")
    item_one.embedding = [1.0, 0.0]
    item_two = _build_item(title="Two")
    item_two.embedding = [0.0, 1.0]
    item_two.embedding_model = "text-embedding-3-large"
    item_two.embedding_input_tokens = 144
    item_two.embedding_retained_tokens = 120
    item_two.embedding_was_truncated = True
    item_two.embedding_truncation_strategy = "tail"
    event = Event(
        id=uuid4(),
        canonical_summary="old",
        epistemic_state="confirmed",
        activity_state="closed",
        provenance_summary={
            "cluster_health": {
                "cluster_cohesion_score": 0.42,
                "split_risk_score": 0.35,
            }
        },
        categories=["legacy"],
        extracted_who=["stale"],
        extracted_what="stale",
        extracted_where="stale",
        extracted_when=datetime.now(tz=UTC),
        has_contradictions=True,
        contradiction_notes="stale",
        extracted_claims={"claim_graph": {"old": True}},
    )
    rows = [
        _EventItemRow(link=EventItem(event_id=event.id, item_id=item_one.id), item=item_one),
        _EventItemRow(link=EventItem(event_id=event.id, item_id=item_two.id), item=item_two),
    ]
    monkeypatch.setattr(event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=rows))
    monkeypatch.setattr(
        event_lineage_module, "_pick_primary_item", AsyncMock(return_value=item_two)
    )
    monkeypatch.setattr(event_lineage_module, "refresh_event_provenance", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_replay_pending", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_claims_stale", AsyncMock())

    await _refresh_event_after_item_change(session=mock_db_session, event=event)

    assert event.canonical_summary == "Two"
    assert event.source_count == 2
    assert event.primary_item_id == item_two.id
    assert event.embedding == [0.0, 1.0]
    assert event.embedding_model == "text-embedding-3-large"
    assert event.embedding_input_tokens == 144
    assert event.embedding_retained_tokens == 120
    assert event.embedding_was_truncated is True
    assert event.embedding_truncation_strategy == "tail"
    assert event.epistemic_state == "emerging"
    assert event.activity_state == "active"
    assert event.provenance_summary["cluster_health"]["cluster_cohesion_score"] == pytest.approx(
        0.0
    )
    assert event.provenance_summary["cluster_health"]["split_risk_score"] == pytest.approx(1.0)
    assert event.categories == []
    assert event.extracted_who is None
    assert event.extracted_what is None
    assert event.extracted_where is None
    assert event.extracted_when is None
    assert event.has_contradictions is False
    assert event.contradiction_notes is None
    assert event.extracted_claims is None


@pytest.mark.asyncio
async def test_refresh_event_after_item_change_resets_singleton_cluster_health(
    mock_db_session, monkeypatch
) -> None:
    item = _build_item(title="One")
    item.embedding = [0.3, 0.4]
    event = Event(
        id=uuid4(),
        canonical_summary="old",
        provenance_summary={
            "cluster_health": {
                "cluster_cohesion_score": 0.42,
                "split_risk_score": 0.35,
            }
        },
    )
    rows = [_EventItemRow(link=EventItem(event_id=event.id, item_id=item.id), item=item)]
    monkeypatch.setattr(event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=rows))
    monkeypatch.setattr(event_lineage_module, "_pick_primary_item", AsyncMock(return_value=item))
    monkeypatch.setattr(event_lineage_module, "refresh_event_provenance", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_replay_pending", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_claims_stale", AsyncMock())

    await _refresh_event_after_item_change(session=mock_db_session, event=event)

    assert event.provenance_summary["cluster_health"]["cluster_cohesion_score"] == pytest.approx(
        1.0
    )
    assert event.provenance_summary["cluster_health"]["split_risk_score"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_refresh_event_after_item_change_clears_retracted_state(
    mock_db_session, monkeypatch
) -> None:
    item = _build_item(title="One")
    event = Event(
        id=uuid4(),
        canonical_summary="old",
        epistemic_state="retracted",
        activity_state="closed",
    )
    rows = [_EventItemRow(link=EventItem(event_id=event.id, item_id=item.id), item=item)]
    monkeypatch.setattr(event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=rows))
    monkeypatch.setattr(event_lineage_module, "_pick_primary_item", AsyncMock(return_value=item))
    monkeypatch.setattr(event_lineage_module, "refresh_event_provenance", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_replay_pending", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_claims_stale", AsyncMock())

    await _refresh_event_after_item_change(session=mock_db_session, event=event)

    assert event.epistemic_state == "emerging"
    assert event.activity_state == "active"


@pytest.mark.asyncio
async def test_refresh_event_after_item_change_preserves_stale_activity_state(
    mock_db_session, monkeypatch
) -> None:
    item = _build_item(title="Old")
    item.published_at = datetime.now(tz=UTC) - timedelta(days=10)
    event = Event(
        id=uuid4(),
        canonical_summary="old",
        activity_state="active",
    )
    rows = [_EventItemRow(link=EventItem(event_id=event.id, item_id=item.id), item=item)]
    monkeypatch.setattr(event_lineage_module, "_load_event_item_rows", AsyncMock(return_value=rows))
    monkeypatch.setattr(event_lineage_module, "_pick_primary_item", AsyncMock(return_value=item))
    monkeypatch.setattr(event_lineage_module, "refresh_event_provenance", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_replay_pending", AsyncMock())
    monkeypatch.setattr(event_lineage_module, "_mark_event_claims_stale", AsyncMock())

    await _refresh_event_after_item_change(session=mock_db_session, event=event)

    assert event.activity_state == "closed"


@pytest.mark.asyncio
async def test_repaired_event_activity_state_defaults_to_active_without_timestamp() -> None:
    event = Event(id=uuid4(), canonical_summary="event", last_mention_at=None)

    assert event_lineage_module._repaired_event_activity_state(event) == "active"


@pytest.mark.asyncio
async def test_repaired_event_activity_state_marks_recently_stale_events_dormant() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="event",
        last_mention_at=datetime.now(tz=UTC) - timedelta(days=3),
    )

    assert event_lineage_module._repaired_event_activity_state(event) == "dormant"


@pytest.mark.asyncio
async def test_close_empty_merged_event_sets_closed_replay_pending_state() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="event",
        embedding=[0.5, 0.6],
        embedding_model="text-embedding-3-large",
        embedding_input_tokens=200,
        embedding_retained_tokens=150,
        embedding_was_truncated=True,
        embedding_truncation_strategy="tail",
        extraction_provenance={"stage": "tier2"},
        extracted_claims={"claim_graph": {}},
        extracted_who=["A"],
        extracted_what="what",
        extracted_where="where",
        extracted_when=datetime.now(tz=UTC),
        categories=["x"],
        has_contradictions=True,
        contradiction_notes="note",
    )

    await _close_empty_merged_event(event)

    assert event.activity_state == "closed"
    assert event.source_count == 0
    assert event.embedding is None
    assert event.embedding_model is None
    assert event.embedding_input_tokens is None
    assert event.embedding_retained_tokens is None
    assert event.embedding_was_truncated is False
    assert event.embedding_truncation_strategy is None
    assert event.extraction_provenance["status"] == "replay_pending"
    assert event.provenance_summary["reason"] == "lineage_repair_empty_cluster"


@pytest.mark.asyncio
async def test_close_empty_merged_event_can_skip_replay_pending_state() -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="event",
        extraction_provenance={"stage": "tier2", "model": "old"},
        extracted_claims={"claim_graph": {}},
        extracted_who=["A"],
        extracted_what="what",
        extracted_where="where",
        extracted_when=datetime.now(tz=UTC),
        categories=["x"],
        has_contradictions=True,
        contradiction_notes="note",
    )

    await _close_empty_merged_event(event, replay_pending=False)

    assert event.activity_state == "closed"
    assert event.extraction_provenance["status"] == "closed"
    assert event.extraction_provenance["original_extraction_provenance"] == {
        "stage": "tier2",
        "model": "old",
    }
    assert event.extracted_claims is None
    assert event.extracted_who is None
    assert not event.categories


@pytest.mark.asyncio
async def test_repair_affected_events_handles_empty_and_restates_active_evidence(
    mock_db_session,
    monkeypatch,
) -> None:
    empty = await _repair_affected_events(session=mock_db_session, events=[Event()], reason="split")
    assert empty == ((), (), ())

    trend = Trend(id=uuid4(), name="Trend", current_log_odds=-2.0)
    evidence_with_trend = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="signal",
        delta_log_odds=Decimal("0.2"),
    )
    evidence_without_trend = TrendEvidence(
        id=uuid4(),
        trend_id=uuid4(),
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="signal",
        delta_log_odds=Decimal("0.1"),
    )
    evidence_without_id = TrendEvidence(
        id=None,
        trend_id=trend.id,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="signal",
        delta_log_odds=Decimal("0.05"),
    )
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(
            all=lambda: [evidence_with_trend, evidence_without_trend, evidence_without_id]
        ),
        SimpleNamespace(all=lambda: [trend]),
    ]
    monkeypatch.setattr(
        event_lineage_module,
        "_load_prior_compensation_by_evidence_id",
        AsyncMock(return_value={evidence_with_trend.id: -0.05}),
    )
    apply_restatement = AsyncMock()
    monkeypatch.setattr(event_lineage_module, "apply_compensating_restatement", apply_restatement)
    monkeypatch.setattr(
        event_lineage_module,
        "_enqueue_event_replay",
        AsyncMock(side_effect=[uuid4(), uuid4()]),
    )

    result = await _repair_affected_events(
        session=mock_db_session,
        events=[Event(id=evidence_with_trend.event_id), Event(id=evidence_without_trend.event_id)],
        reason="merge",
    )

    assert evidence_with_trend.is_invalidated is True
    assert evidence_without_trend.is_invalidated is True
    assert evidence_without_id.is_invalidated is True
    assert apply_restatement.await_count == 2
    assert result[0] == (evidence_with_trend.id,)
    assert result[1] == (evidence_with_trend.event_id, evidence_without_trend.event_id)
    assert len(result[2]) == 2


@pytest.mark.asyncio
async def test_repair_affected_events_raises_when_replay_enqueue_fails(
    mock_db_session,
    monkeypatch,
) -> None:
    trend = Trend(id=uuid4(), name="Trend", current_log_odds=-2.0)
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="signal",
        delta_log_odds=Decimal("0.2"),
    )
    mock_db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [evidence]),
        SimpleNamespace(all=lambda: [trend]),
    ]
    monkeypatch.setattr(
        event_lineage_module,
        "_load_prior_compensation_by_evidence_id",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(event_lineage_module, "apply_compensating_restatement", AsyncMock())
    monkeypatch.setattr(
        event_lineage_module,
        "_enqueue_event_replay",
        AsyncMock(return_value=None),
    )

    with pytest.raises(RuntimeError, match="requires replay queue items"):
        await _repair_affected_events(
            session=mock_db_session,
            events=[Event(id=evidence.event_id)],
            reason="merge",
        )


def test_select_from_active_evidence_builds_expected_query() -> None:
    query_text = str(select_from_active_evidence(event_ids=(uuid4(),))).lower()

    assert "trend_evidence.is_invalidated is false" in query_text
    assert "order by trend_evidence.created_at" in query_text


@pytest.mark.asyncio
async def test_load_trend_and_compensation_helpers(mock_db_session, monkeypatch) -> None:
    trend = Trend(id=uuid4(), name="Trend", current_log_odds=-2.0)
    evidence = TrendEvidence(
        id=uuid4(),
        trend_id=trend.id,
        event_id=uuid4(),
        event_claim_id=uuid4(),
        signal_type="signal",
        delta_log_odds=Decimal("0.2"),
    )
    mock_db_session.scalars.side_effect = [SimpleNamespace(all=lambda: [trend])]
    monkeypatch.setattr(
        event_lineage_module,
        "restatement_compensation_totals_by_evidence_id",
        AsyncMock(return_value={evidence.id: -0.05}),
    )

    assert await _load_trends_for_evidence(session=mock_db_session, trend_ids=set()) == {}
    loaded = await _load_trends_for_evidence(session=mock_db_session, trend_ids={trend.id})
    assert loaded == {trend.id: trend}
    assert await _load_prior_compensation_by_evidence_id(
        session=mock_db_session,
        evidences=[evidence],
    ) == {evidence.id: -0.05}
    assert _invalidation_compensation_delta(
        evidence=evidence,
        prior_compensation_by_evidence_id={evidence.id: -0.05},
    ) == pytest.approx(-0.15)


@pytest.mark.asyncio
async def test_mark_event_claims_stale_and_replay_pending(mock_db_session) -> None:
    claim = EventClaim(
        event_id=uuid4(), claim_key="__event__", claim_text="claim", claim_type="fallback"
    )
    claim.is_active = True
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [claim])
    event = Event(id=uuid4(), canonical_summary="event", extraction_provenance={"old": True})

    await _mark_event_claims_stale(session=mock_db_session, event_id=claim.event_id)
    await _mark_event_replay_pending(event=event, reason="repair")

    assert claim.is_active is False
    assert event.extraction_provenance["reason"] == "repair"
    assert event.extracted_claims is None


@pytest.mark.asyncio
async def test_enqueue_event_replay_handles_missing_event_success_and_conflict(
    mock_db_session,
) -> None:
    @asynccontextmanager
    async def _begin_nested():
        yield

    event = Event(id=uuid4(), canonical_summary="event", extraction_provenance={"old": True})
    mock_db_session.get = AsyncMock(side_effect=[None, event, event])
    mock_db_session.scalars = AsyncMock(return_value=SimpleNamespace(all=list))
    mock_db_session.begin_nested = _begin_nested
    mock_db_session.flush = AsyncMock(side_effect=[None, IntegrityError("x", "y", "z")])
    mock_db_session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(rowcount=0),
            SimpleNamespace(rowcount=0),
            SimpleNamespace(rowcount=1),
        ]
    )

    assert (
        await _enqueue_event_replay(session=mock_db_session, event_id=uuid4(), reason="split")
        is None
    )
    assert (
        await _enqueue_event_replay(session=mock_db_session, event_id=event.id, reason="split")
        is not None
    )
    reset_request_id = await _enqueue_event_replay(
        session=mock_db_session,
        event_id=event.id,
        reason="split",
    )
    assert reset_request_id is not None
    assert mock_db_session.execute.await_count == 3
    reset_statement = mock_db_session.execute.await_args_list[-1].args[0]
    compiled = reset_statement.compile()
    assert "update llm_replay_queue" in str(reset_statement).lower()
    assert compiled.params["event_id_1"] == event.id
    assert compiled.params["status_1"] == "processing"
    assert compiled.params["status"] == "pending"
    assert compiled.params["priority"] == 500
    assert compiled.params["details"] == {
        "reason": "event_lineage_repair",
        "repair_kind": "split",
        "replay_request_id": str(reset_request_id),
        "original_extraction_provenance": {"old": True},
    }


@pytest.mark.asyncio
async def test_enqueue_event_replay_resets_existing_pending_row(mock_db_session) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="event",
        extraction_provenance={
            "status": "replay_pending",
            "original_extraction_provenance": {"stage": "tier2"},
        },
    )
    mock_db_session.get = AsyncMock(return_value=event)
    mock_db_session.scalars = AsyncMock(return_value=SimpleNamespace(all=list))
    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))

    replay_request_id = await _enqueue_event_replay(
        session=mock_db_session,
        event_id=event.id,
        reason="merge",
    )
    assert replay_request_id is not None
    statement = mock_db_session.execute.await_args.args[0]
    compiled = statement.compile()
    assert "update llm_replay_queue" in str(statement).lower()
    assert compiled.params["event_id_1"] == event.id
    assert compiled.params["status_1"] == "processing"
    assert compiled.params["status"] == "pending"
    assert compiled.params["details"] == {
        "reason": "event_lineage_repair",
        "repair_kind": "merge",
        "replay_request_id": str(replay_request_id),
        "original_extraction_provenance": {"stage": "tier2"},
    }


@pytest.mark.asyncio
async def test_enqueue_event_replay_supersedes_prior_request_ids_on_reset(
    mock_db_session,
    monkeypatch,
) -> None:
    old_request_id = uuid4()
    event = Event(id=uuid4(), canonical_summary="event", extraction_provenance={"old": True})
    mock_db_session.get = AsyncMock(return_value=event)
    mock_db_session.scalars = AsyncMock(
        return_value=SimpleNamespace(all=lambda: [{"replay_request_id": str(old_request_id)}])
    )
    mock_db_session.execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))
    mark_superseded = AsyncMock()
    monkeypatch.setattr(
        event_lineage_replay_module,
        "mark_lineages_superseded_for_replay_requests",
        mark_superseded,
    )

    replay_request_id = await _enqueue_event_replay(
        session=mock_db_session,
        event_id=event.id,
        reason="merge",
    )

    assert replay_request_id is not None
    mark_superseded.assert_awaited_once_with(
        session=mock_db_session,
        replay_request_ids=(old_request_id,),
    )


@pytest.mark.asyncio
async def test_enqueue_event_replay_does_not_reset_processing_row(mock_db_session) -> None:
    event = Event(id=uuid4(), canonical_summary="event", extraction_provenance={"old": True})

    @asynccontextmanager
    async def _begin_nested():
        yield

    mock_db_session.get = AsyncMock(return_value=event)
    mock_db_session.scalars = AsyncMock(return_value=SimpleNamespace(all=list))
    mock_db_session.begin_nested = _begin_nested
    mock_db_session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(rowcount=0),
            SimpleNamespace(rowcount=0),
        ]
    )
    mock_db_session.flush = AsyncMock(side_effect=[IntegrityError("x", "y", "z")])

    assert (
        await _enqueue_event_replay(session=mock_db_session, event_id=event.id, reason="merge")
        is None
    )
    assert mock_db_session.execute.await_count == 2


@pytest.mark.asyncio
async def test_enqueue_event_replay_conflict_recovery_uses_processing_guard(
    mock_db_session,
) -> None:
    @asynccontextmanager
    async def _begin_nested():
        yield

    event = Event(id=uuid4(), canonical_summary="event", extraction_provenance={"old": True})
    mock_db_session.get = AsyncMock(return_value=event)
    mock_db_session.scalars = AsyncMock(return_value=SimpleNamespace(all=list))
    mock_db_session.begin_nested = _begin_nested
    mock_db_session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(rowcount=0),
            SimpleNamespace(rowcount=0),
        ]
    )
    mock_db_session.flush = AsyncMock(side_effect=[IntegrityError("x", "y", "z")])

    assert (
        await _enqueue_event_replay(session=mock_db_session, event_id=event.id, reason="merge")
        is None
    )
    statement = mock_db_session.execute.await_args_list[0].args[0]
    compiled = statement.compile()
    assert compiled.params["event_id_1"] == event.id
    assert compiled.params["status_1"] == "processing"


@pytest.mark.asyncio
async def test_delete_event_replay_queue_items_executes_delete(
    mock_db_session,
    monkeypatch,
) -> None:
    event_id = uuid4()
    deleted_request_id = uuid4()
    mock_db_session.execute.return_value = SimpleNamespace(rowcount=1)
    mock_db_session.scalars = AsyncMock(
        return_value=SimpleNamespace(all=lambda: [{"replay_request_id": str(deleted_request_id)}])
    )
    mark_superseded = AsyncMock()
    monkeypatch.setattr(
        event_lineage_replay_module,
        "mark_lineages_superseded_for_replay_requests",
        mark_superseded,
    )

    await _delete_event_replay_queue_items(session=mock_db_session, event_id=event_id)

    statement = mock_db_session.execute.await_args.args[0]
    assert "delete from llm_replay_queue" in str(statement).lower()
    assert statement.compile().params["stage_1"] == "tier2"
    assert statement.compile().params["event_id_1"] == event_id
    assert statement.compile().params["status_1"] == "processing"
    mark_superseded.assert_awaited_once_with(
        session=mock_db_session,
        replay_request_ids=(deleted_request_id,),
    )


@pytest.mark.asyncio
async def test_delete_event_replay_queue_items_rejects_processing_row(mock_db_session) -> None:
    event_id = uuid4()
    mock_db_session.execute.return_value = SimpleNamespace(rowcount=0)
    mock_db_session.scalars = AsyncMock(return_value=SimpleNamespace(all=list))
    mock_db_session.scalar = AsyncMock(return_value=uuid4())

    with pytest.raises(RuntimeError, match="source replay is processing"):
        await _delete_event_replay_queue_items(session=mock_db_session, event_id=event_id)


@pytest.mark.asyncio
async def test_delete_event_replay_queue_items_allows_missing_row(mock_db_session) -> None:
    event_id = uuid4()
    mock_db_session.execute.return_value = SimpleNamespace(rowcount=0)
    mock_db_session.scalars = AsyncMock(return_value=SimpleNamespace(all=list))
    mock_db_session.scalar = AsyncMock(return_value=None)

    await _delete_event_replay_queue_items(session=mock_db_session, event_id=event_id)


@pytest.mark.asyncio
async def test_mark_lineages_superseded_for_replay_requests_updates_matching_lineages() -> None:
    replay_request_id = uuid4()
    matching_lineage = EventLineage(
        details={"replay_request_ids": [str(replay_request_id)], "status": "replay_pending"}
    )
    untouched_lineage = EventLineage(details={"replay_request_ids": [str(uuid4())]})
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(
        all=lambda: [matching_lineage, untouched_lineage]
    )

    await mark_lineages_superseded_for_replay_requests(
        session=session,
        replay_request_ids=(replay_request_id,),
    )

    assert matching_lineage.details["status"] == "replay_superseded"
    assert untouched_lineage.details.get("status") is None


@pytest.mark.asyncio
async def test_mark_lineages_superseded_for_replay_requests_keeps_terminal_statuses() -> None:
    replay_request_id = uuid4()
    complete_lineage = EventLineage(
        details={"replay_request_ids": [str(replay_request_id)], "status": "replay_complete"}
    )
    error_lineage = EventLineage(
        details={"replay_request_ids": [str(replay_request_id)], "status": "replay_error"}
    )
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [complete_lineage, error_lineage])

    await mark_lineages_superseded_for_replay_requests(
        session=session,
        replay_request_ids=(replay_request_id,),
    )

    assert complete_lineage.details["status"] == "replay_complete"
    assert error_lineage.details["status"] == "replay_error"


@pytest.mark.asyncio
async def test_mark_lineages_superseded_for_replay_requests_returns_early_without_ids() -> None:
    session = AsyncMock()

    await mark_lineages_superseded_for_replay_requests(session=session, replay_request_ids=())

    session.scalars.assert_not_awaited()


def test_replay_helper_utilities_clear_stale_fields_and_preserve_original_provenance() -> None:
    event = Event(
        canonical_summary="event",
        extraction_provenance={
            "status": "replay_pending",
            "original_extraction_provenance": {"stage": "tier2"},
        },
        extracted_claims={"claim_graph": {}},
        extracted_who=["A"],
        extracted_what="what",
        extracted_where="where",
        extracted_when=datetime.now(tz=UTC),
        categories=["x"],
        has_contradictions=True,
        contradiction_notes="note",
    )

    clear_stale_event_extractions(event)

    assert event.extracted_claims is None
    assert event.extracted_who is None
    assert event.extracted_what is None
    assert event.extracted_where is None
    assert event.extracted_when is None
    assert event.categories == []
    assert event.has_contradictions is False
    assert event.contradiction_notes is None
    assert replay_source_provenance(event) == {"stage": "tier2"}
    event.extraction_provenance = {"status": "done", "model": "tier2"}
    assert replay_source_provenance(event) == {"status": "done", "model": "tier2"}
    assert event_lineage_replay_module._extract_replay_request_ids(
        [{"replay_request_id": uuid4()}, {"replay_request_id": "bad"}, None]
    )


def test_replay_source_provenance_unwraps_nested_pending_wrappers() -> None:
    event = Event(
        canonical_summary="event",
        extraction_provenance={
            "status": "replay_pending",
            "original_extraction_provenance": {
                "status": "replay_pending",
                "original_extraction_provenance": {"status": "done", "model": "tier2"},
            },
        },
    )

    assert replay_source_provenance(event) == {"status": "done", "model": "tier2"}


@pytest.mark.asyncio
async def test_pick_primary_item_and_basic_helpers(mock_db_session) -> None:
    item = _build_item(title="Primary item")
    item.fetched_at = datetime.now(tz=UTC)
    mock_db_session.scalar = AsyncMock(side_effect=[item, None])

    with pytest.raises(ValueError, match="at least one item"):
        await _pick_primary_item(session=mock_db_session, item_ids=())

    resolved = await _pick_primary_item(session=mock_db_session, item_ids=(item.id,))
    assert resolved is item
    with pytest.raises(ValueError, match="unable to resolve primary item"):
        await _pick_primary_item(session=mock_db_session, item_ids=(item.id,))

    assert _build_canonical_summary(item) == "Primary item"
    item.title = "   "
    item.raw_content = "x" * 450
    assert len(_build_canonical_summary(item)) == 400
    assert _item_timestamp(item) == item.published_at
    item.published_at = None
    assert _item_timestamp(item) == item.fetched_at
    item.fetched_at = None
    assert _item_timestamp(item).tzinfo == UTC


@pytest.mark.asyncio
async def test_pick_primary_item_prefers_current_primary_on_credibility_ties(
    mock_db_session,
) -> None:
    item = _build_item(title="Primary item")
    current_primary_item_id = uuid4()
    mock_db_session.scalar = AsyncMock(return_value=item)

    await _pick_primary_item(
        session=mock_db_session,
        item_ids=(item.id, uuid4()),
        current_primary_item_id=current_primary_item_id,
    )

    statement = mock_db_session.scalar.await_args.args[0]
    assert "CASE WHEN" in str(statement)
    assert current_primary_item_id in statement.compile().params.values()
    with pytest.raises(ValueError, match="must have an id"):
        _require_event_id(Event(canonical_summary="missing"))
