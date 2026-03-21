from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.storage.models import LLMReplayQueueItem, Trend
from src.workers import _task_maintenance

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_replay_one_degraded_item_passes_provenance_derivation() -> None:
    event_id = uuid4()
    queue_item_id = uuid4()
    replay_request_id = uuid4()
    event = SimpleNamespace(id=event_id)
    lineage = SimpleNamespace(
        details={
            "replay_enqueued_event_ids": [str(event_id)],
            "replay_request_ids": [str(replay_request_id)],
            "status": "replay_pending",
        }
    )
    item = SimpleNamespace(
        id=queue_item_id,
        event_id=event_id,
        details={"original_extraction_provenance": {"stage": "tier2"}},
        status="pending",
        processed_at=None,
        locked_at="locked",
        locked_by="worker",
        last_error="old",
    )
    session = AsyncMock()
    session.get.return_value = event
    session.scalars.return_value = SimpleNamespace(all=lambda: [lineage])
    session.execute.return_value = SimpleNamespace(
        all=lambda: [
            (queue_item_id, event_id, "done", {"replay_request_id": str(replay_request_id)})
        ]
    )
    pipeline = SimpleNamespace(_apply_trend_impacts=AsyncMock(return_value=(2, 1)))
    deps = SimpleNamespace(Event=object(), settings=SimpleNamespace(LLM_TIER2_MODEL="tier2-model"))
    captured: dict[str, object] = {}

    class _Tier2:
        async def classify_event(
            self,
            *,
            event: object,
            trends: list[object],
            provenance_derivation: dict[str, object],
        ) -> None:
            captured["event"] = event
            captured["trends"] = trends
            captured["provenance_derivation"] = provenance_derivation

    now = datetime(2026, 3, 21, tzinfo=UTC)
    trends = [SimpleNamespace(id="trend-1")]

    processed = await _task_maintenance._replay_one_degraded_item(
        deps=deps,
        session=session,
        tier2=_Tier2(),
        pipeline=pipeline,
        trends=trends,
        item=item,
        now=now,
    )

    assert processed is True
    assert captured["event"] is event
    assert captured["trends"] == trends
    assert captured["provenance_derivation"] == {
        "source": "replay_queue",
        "queue_item_id": str(queue_item_id),
        "original_extraction_provenance": {"stage": "tier2"},
    }
    assert item.status == "done"
    assert item.processed_at == now
    assert item.locked_at is None
    assert item.locked_by is None
    assert item.last_error is None
    assert item.details["replay_result"] == {
        "impacts_seen": 2,
        "updates_applied": 1,
        "processed_at": now.isoformat(),
        "model": "tier2-model",
    }
    session.flush.assert_awaited_once()
    assert lineage.details["status"] == "replay_complete"


@pytest.mark.asyncio
async def test_sync_lineage_replay_status_leaves_pending_when_other_replays_not_done() -> None:
    event_id = uuid4()
    other_event_id = uuid4()
    lineage = SimpleNamespace(
        details={
            "replay_enqueued_event_ids": [str(event_id), str(other_event_id)],
            "status": "replay_pending",
        }
    )
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [lineage])
    session.execute.return_value = SimpleNamespace(
        all=lambda: [(event_id, "done"), (other_event_id, "pending")]
    )

    await _task_maintenance._sync_lineage_replay_status(session=session, event_id=event_id)

    assert lineage.details["status"] == "replay_pending"


@pytest.mark.asyncio
async def test_sync_lineage_replay_status_marks_error_when_any_replay_errors() -> None:
    event_id = uuid4()
    other_event_id = uuid4()
    lineage = SimpleNamespace(
        details={
            "replay_enqueued_event_ids": [str(event_id), str(other_event_id)],
            "status": "replay_pending",
        }
    )
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [lineage])
    session.execute.return_value = SimpleNamespace(
        all=lambda: [(event_id, "done"), (other_event_id, "error")]
    )

    await _task_maintenance._sync_lineage_replay_status(session=session, event_id=event_id)

    assert lineage.details["status"] == "replay_error"


@pytest.mark.asyncio
async def test_sync_lineage_replay_status_marks_superseded_when_queue_row_was_deleted() -> None:
    event_id = uuid4()
    other_event_id = uuid4()
    replay_request_id = uuid4()
    other_replay_request_id = uuid4()
    lineage = SimpleNamespace(
        details={
            "replay_enqueued_event_ids": [str(event_id), str(other_event_id)],
            "replay_request_ids": [str(replay_request_id), str(other_replay_request_id)],
            "status": "replay_pending",
        }
    )
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [lineage])
    session.execute.return_value = SimpleNamespace(
        all=lambda: [(uuid4(), event_id, "done", {"replay_request_id": str(replay_request_id)})]
    )

    await _task_maintenance._sync_lineage_replay_status(session=session, event_id=event_id)

    assert lineage.details["status"] == "replay_superseded"


@pytest.mark.asyncio
async def test_sync_lineage_replay_status_keeps_terminal_status_when_queue_row_is_deleted() -> None:
    event_id = uuid4()
    replay_request_id = uuid4()
    complete_lineage = SimpleNamespace(
        details={
            "replay_enqueued_event_ids": [str(event_id)],
            "replay_request_ids": [str(replay_request_id)],
            "status": "replay_complete",
        }
    )
    error_lineage = SimpleNamespace(
        details={
            "replay_enqueued_event_ids": [str(event_id)],
            "replay_request_ids": [str(replay_request_id)],
            "status": "replay_error",
        }
    )
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [complete_lineage, error_lineage])
    session.execute.return_value = SimpleNamespace(all=list)

    await _task_maintenance._sync_lineage_replay_status(session=session, event_id=event_id)

    assert complete_lineage.details["status"] == "replay_complete"
    assert error_lineage.details["status"] == "replay_error"


@pytest.mark.asyncio
async def test_sync_lineage_replay_status_skips_lineages_without_replay_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    lineage = SimpleNamespace(
        details={"replay_enqueued_event_ids": [str(event_id)], "status": "replay_pending"}
    )
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [lineage])
    session.execute.return_value = SimpleNamespace(all=list)
    monkeypatch.setattr(_task_maintenance, "_parse_lineage_replay_ids", lambda _: ())

    await _task_maintenance._sync_lineage_replay_status(session=session, event_id=event_id)

    assert lineage.details["status"] == "replay_pending"


@pytest.mark.asyncio
async def test_replay_degraded_events_async_marks_lineage_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        event_id=uuid4(),
        status="pending",
        locked_at=None,
        locked_by=None,
        attempt_count=0,
        last_attempt_at=None,
        details={},
        last_error=None,
        processed_at=None,
        priority=1,
        enqueued_at=datetime(2026, 3, 21, tzinfo=UTC),
    )
    session = AsyncMock()
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [item]),
        SimpleNamespace(all=list),
    ]

    class _SessionContext:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    sync_status = AsyncMock()
    monkeypatch.setattr(
        _task_maintenance,
        "_replay_one_degraded_item",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(_task_maintenance, "_sync_lineage_replay_status", sync_status)

    class _Tier2Classifier:
        def __init__(self, *, session, model, secondary_model) -> None:
            pass

    class _Pipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            pass

    deps = SimpleNamespace(
        settings=SimpleNamespace(LLM_DEGRADED_MODE_ENABLED=False, LLM_TIER2_MODEL="tier2-model"),
        async_session_maker=lambda: _SessionContext(),
        select=select,
        LLMReplayQueueItem=LLMReplayQueueItem,
        Trend=Trend,
        Tier2Classifier=_Tier2Classifier,
        ProcessingPipeline=_Pipeline,
        asyncio=SimpleNamespace(to_thread=AsyncMock()),
    )

    result = await _task_maintenance.replay_degraded_events_async(deps=deps, limit=1)

    assert result == {"status": "ok", "task": "replay_degraded_events", "drained": 1, "errors": 1}
    assert item.status == "error"
    assert item.last_error == "boom"
    session.flush.assert_awaited()
    sync_status.assert_awaited_once_with(session=session, event_id=item.event_id)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_replay_degraded_events_async_respects_disable_flag_for_non_lineage_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lineage_item = SimpleNamespace(
        event_id=uuid4(),
        status="pending",
        locked_at=None,
        locked_by=None,
        attempt_count=0,
        last_attempt_at=None,
        details={"reason": "event_lineage_repair"},
        last_error=None,
        processed_at=None,
        priority=5,
        enqueued_at=datetime(2026, 3, 21, tzinfo=UTC),
    )
    session = AsyncMock()
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [lineage_item]),
        SimpleNamespace(all=list),
    ]

    class _SessionContext:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    replay_one = AsyncMock(return_value=True)
    monkeypatch.setattr(_task_maintenance, "_replay_one_degraded_item", replay_one)

    class _Tier2Classifier:
        def __init__(self, *, session, model, secondary_model) -> None:
            pass

    class _Pipeline:
        def __init__(self, *, session, tier2_classifier, degraded_llm_tracker) -> None:
            pass

    deps = SimpleNamespace(
        settings=SimpleNamespace(
            LLM_DEGRADED_MODE_ENABLED=False,
            LLM_DEGRADED_REPLAY_ENABLED=False,
            LLM_TIER2_MODEL="tier2-model",
        ),
        async_session_maker=lambda: _SessionContext(),
        select=select,
        LLMReplayQueueItem=LLMReplayQueueItem,
        Trend=Trend,
        Tier2Classifier=_Tier2Classifier,
        ProcessingPipeline=_Pipeline,
        asyncio=SimpleNamespace(to_thread=AsyncMock()),
    )

    result = await _task_maintenance.replay_degraded_events_async(deps=deps, limit=5)

    assert result == {"status": "ok", "task": "replay_degraded_events", "drained": 1, "errors": 0}
    assert lineage_item.status == "processing"
    replay_one.assert_awaited_once()
    assert replay_one.await_args.kwargs["item"] is lineage_item
    query_text = str(session.scalars.await_args_list[0].args[0]).lower()
    assert "details[:details_1]" in query_text
    assert "for update" in query_text


def test_parse_lineage_replay_ids_skips_invalid_values() -> None:
    parsed = _task_maintenance._parse_lineage_replay_ids(
        SimpleNamespace(details={"replay_enqueued_event_ids": [uuid4(), "not-a-uuid", None]})
    )

    assert len(parsed) == 1


def test_parse_lineage_queue_item_ids_skips_invalid_values() -> None:
    parsed = _task_maintenance._parse_lineage_queue_item_ids(
        SimpleNamespace(details={"replay_queue_item_ids": [uuid4(), "not-a-uuid", None]})
    )

    assert len(parsed) == 1


def test_parse_lineage_replay_request_ids_skips_invalid_values() -> None:
    parsed = _task_maintenance._parse_lineage_replay_request_ids(
        SimpleNamespace(details={"replay_request_ids": [uuid4(), "not-a-uuid", None]})
    )

    assert len(parsed) == 1


def test_build_replay_status_maps_handles_missing_identifiers() -> None:
    event_id = uuid4()
    queue_item_id = uuid4()
    replay_request_id = uuid4()

    status_by_event_id, status_by_queue_item_id, status_by_request_id = (
        _task_maintenance._build_replay_status_maps(
            [
                (None, event_id, "pending", {"replay_request_id": "not-a-uuid"}),
                (queue_item_id, None, "error", {"replay_request_id": str(replay_request_id)}),
                (None, "done"),
            ]
        )
    )

    assert status_by_event_id == {str(event_id): "pending"}
    assert status_by_queue_item_id == {str(queue_item_id): "error"}
    assert status_by_request_id == {str(replay_request_id): "error"}


def test_build_replay_status_maps_handles_legacy_queue_item_rows() -> None:
    event_id = uuid4()
    queue_item_id = uuid4()

    status_by_event_id, status_by_queue_item_id, status_by_request_id = (
        _task_maintenance._build_replay_status_maps(
            [
                (queue_item_id, event_id, "done"),
            ]
        )
    )

    assert status_by_event_id == {str(event_id): "done"}
    assert status_by_queue_item_id == {str(queue_item_id): "done"}
    assert status_by_request_id == {}


def test_build_replay_status_maps_handles_legacy_rows_with_missing_identifiers() -> None:
    event_id = uuid4()
    queue_item_id = uuid4()

    status_by_event_id, status_by_queue_item_id, status_by_request_id = (
        _task_maintenance._build_replay_status_maps(
            [
                (None, event_id, "pending"),
                (queue_item_id, None, "error"),
            ]
        )
    )

    assert status_by_event_id == {str(event_id): "pending"}
    assert status_by_queue_item_id == {str(queue_item_id): "error"}
    assert status_by_request_id == {}


def test_apply_lineage_replay_status_supports_legacy_queue_item_tracking() -> None:
    queue_item_id = uuid4()
    lineage = SimpleNamespace(
        details={
            "replay_queue_item_ids": [str(queue_item_id)],
            "status": "replay_pending",
        }
    )

    _task_maintenance._apply_lineage_replay_status(
        lineage=lineage,
        status_by_event_id={},
        status_by_queue_item_id={str(queue_item_id): "done"},
        status_by_request_id={},
    )

    assert lineage.details["status"] == "replay_complete"
