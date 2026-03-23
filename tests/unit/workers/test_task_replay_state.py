from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from src.storage.models import LLMReplayQueueItem, Trend
from src.workers import _task_maintenance
from src.workers import _task_replay as replay_helpers

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_persist_failure_state_retries_with_refreshed_pending_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_now = datetime(2026, 3, 21, 12, 0, tzinfo=UTC)
    retry_now = initial_now + timedelta(minutes=5)
    item_id = uuid4()
    item = SimpleNamespace(id=item_id, status="pending")
    refreshed_item = SimpleNamespace(id=item_id, status="pending")
    session = AsyncMock()
    session.get = AsyncMock(return_value=refreshed_item)
    persist_calls: list[tuple[object, datetime]] = []

    async def persist_failure(**kwargs: object) -> None:
        persist_calls.append((kwargs["item"], kwargs["now"]))
        if len(persist_calls) == 1:
            raise OperationalError("flush", {}, Exception("drop"))

    class _RetryDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            del tz
            return retry_now

    monkeypatch.setattr(replay_helpers, "datetime", _RetryDateTime)

    persisted_item = await replay_helpers.persist_failure_state(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        exc=ValueError("boom"),
        now=initial_now,
        attempt_count_override=2,
        dbapi_error_cls=OperationalError,
        persist_failure=persist_failure,
    )

    assert persisted_item is refreshed_item
    assert persist_calls == [(item, initial_now), (refreshed_item, retry_now)]
    session.rollback.assert_awaited_once()
    session.get.assert_awaited_once_with(LLMReplayQueueItem, item_id, with_for_update=True)


@pytest.mark.asyncio
async def test_persist_failure_state_stops_when_recovery_row_is_missing() -> None:
    item_id = uuid4()
    item = SimpleNamespace(id=item_id, status="pending")
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    async def persist_failure(**kwargs: object) -> None:
        del kwargs
        raise OperationalError("flush", {}, Exception("drop"))

    persisted_item = await replay_helpers.persist_failure_state(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        exc=ValueError("boom"),
        now=datetime(2026, 3, 21, tzinfo=UTC),
        attempt_count_override=2,
        dbapi_error_cls=OperationalError,
        persist_failure=persist_failure,
    )

    assert persisted_item is None
    session.rollback.assert_awaited_once()
    session.get.assert_awaited_once_with(LLMReplayQueueItem, item_id, with_for_update=True)


@pytest.mark.asyncio
async def test_persist_failure_state_returns_none_after_two_dbapi_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_now = datetime(2026, 3, 21, 12, 0, tzinfo=UTC)
    retry_now = initial_now + timedelta(minutes=5)
    item_id = uuid4()
    item = SimpleNamespace(id=item_id, status="pending")
    refreshed_item = SimpleNamespace(id=item_id, status="pending")
    session = AsyncMock()
    session.get = AsyncMock(return_value=refreshed_item)
    persist_calls: list[datetime] = []

    async def persist_failure(**kwargs: object) -> None:
        persist_calls.append(kwargs["now"])
        raise OperationalError("flush", {}, Exception("drop"))

    class _RetryDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            del tz
            return retry_now

    monkeypatch.setattr(replay_helpers, "datetime", _RetryDateTime)

    persisted_item = await replay_helpers.persist_failure_state(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        exc=ValueError("boom"),
        now=initial_now,
        attempt_count_override=2,
        dbapi_error_cls=OperationalError,
        persist_failure=persist_failure,
    )

    assert persisted_item is None
    assert persist_calls == [initial_now, retry_now]
    assert session.rollback.await_count == 2
    assert session.get.await_count == 2


@pytest.mark.asyncio
async def test_process_replay_item_treats_done_status_as_committed_after_commit_dbapi_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="done",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=OperationalError("commit", {}, Exception("drop")))
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", AsyncMock())
    monkeypatch.setattr(
        replay_helpers,
        "fresh_replay_state",
        AsyncMock(
            return_value={
                "status": "done",
                "attempt_count": 2,
                "last_attempt_at": None,
                "processed_at": None,
                "last_error": None,
                "replay_failure": None,
                "replay_result": None,
            }
        ),
    )

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is False
    session.rollback.assert_awaited_once()
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_replay_item_treats_error_status_as_committed_after_commit_dbapi_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="error",
        details={"replay_failure": {"disposition": "manual_review"}},
        last_attempt_at=None,
        processed_at=None,
        last_error="Event not found",
    )
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=OperationalError("commit", {}, Exception("drop")))
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(side_effect=ValueError("boom"))
    )
    monkeypatch.setattr(replay_helpers, "persist_failure_state", AsyncMock(return_value=item))
    monkeypatch.setattr(
        replay_helpers,
        "fresh_replay_state",
        AsyncMock(return_value=replay_helpers.serialize_replay_state(item=item)),
    )

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_replay_item_requeues_after_commit_dbapi_error_when_state_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="done",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    refreshed_item = SimpleNamespace(id=item.id, attempt_count=2, status="pending")
    session = AsyncMock()
    session.commit = AsyncMock(
        side_effect=[OperationalError("commit", {}, Exception("drop")), None]
    )
    session.get = AsyncMock(return_value=refreshed_item)
    handle_failure = AsyncMock()
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", handle_failure)
    monkeypatch.setattr(replay_helpers, "fresh_replay_state", AsyncMock(return_value=None))

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.get.assert_awaited_with(LLMReplayQueueItem, item.id, with_for_update=True)
    handle_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_replay_item_stops_when_dbapi_recovery_row_is_not_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(id=uuid4(), attempt_count=2, status="processing", details={})
    session = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(status="processing"))
    db_failure = OperationalError("select 1", {}, Exception("db down"))
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(side_effect=db_failure)
    )
    handle_failure = AsyncMock()
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", handle_failure)

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    handle_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_replay_item_stops_when_dbapi_failure_state_cannot_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(id=uuid4(), attempt_count=2, status="processing", details={})
    refreshed_item = SimpleNamespace(id=item.id, attempt_count=2, status="pending")
    session = AsyncMock()
    session.get = AsyncMock(return_value=refreshed_item)
    db_failure = OperationalError("select 1", {}, Exception("db down"))
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(side_effect=db_failure)
    )
    monkeypatch.setattr(replay_helpers, "persist_failure_state", AsyncMock(return_value=None))

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_replay_item_stops_when_non_db_failure_state_cannot_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(id=uuid4(), attempt_count=2, status="processing", details={})
    monkeypatch.setattr(
        _task_maintenance,
        "_replay_one_degraded_item",
        AsyncMock(side_effect=ValueError("Event not found")),
    )
    monkeypatch.setattr(replay_helpers, "persist_failure_state", AsyncMock(return_value=None))
    session = AsyncMock()

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_replay_item_preserves_original_failure_during_commit_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="processing",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    refreshed_item = SimpleNamespace(id=item.id, attempt_count=2, status="pending")
    session = AsyncMock()
    session.commit = AsyncMock(
        side_effect=[OperationalError("commit", {}, Exception("drop")), None]
    )
    session.get = AsyncMock(return_value=refreshed_item)
    handle_failure = AsyncMock()
    original_failure = ValueError("Event not found")
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(side_effect=original_failure)
    )
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", handle_failure)
    monkeypatch.setattr(replay_helpers, "fresh_replay_state", AsyncMock(return_value=None))

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    assert handle_failure.await_count == 2
    assert handle_failure.await_args_list[0].kwargs["exc"] is original_failure
    assert handle_failure.await_args_list[1].kwargs["exc"] is original_failure


@pytest.mark.asyncio
async def test_process_replay_item_uses_current_failure_time_for_retry_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_time = datetime(2026, 3, 21, 12, 0, tzinfo=UTC)
    failure_time = start_time + timedelta(minutes=10)
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=1,
        status="processing",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    session = AsyncMock()
    session.commit = AsyncMock(return_value=None)
    handle_failure = AsyncMock()
    monkeypatch.setattr(
        _task_maintenance,
        "_replay_one_degraded_item",
        AsyncMock(side_effect=ConnectionError("slow")),
    )
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", handle_failure)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            del tz
            return failure_time

    monkeypatch.setattr(_task_maintenance, "datetime", _FakeDateTime)

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=start_time,
    )

    assert had_error is True
    assert handle_failure.await_args.kwargs["now"] == failure_time


@pytest.mark.asyncio
async def test_process_replay_item_stops_when_commit_dbapi_error_row_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="done",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=OperationalError("commit", {}, Exception("drop")))
    session.get = AsyncMock(return_value=None)
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", AsyncMock())
    monkeypatch.setattr(replay_helpers, "fresh_replay_state", AsyncMock(return_value=None))

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.get.assert_awaited_with(LLMReplayQueueItem, item.id, with_for_update=True)


@pytest.mark.asyncio
async def test_process_replay_item_stops_commit_recovery_when_row_is_no_longer_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="done",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=OperationalError("commit", {}, Exception("drop")))
    session.get = AsyncMock(return_value=SimpleNamespace(status="done"))
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(return_value=True)
    )
    handle_failure = AsyncMock()
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", handle_failure)
    monkeypatch.setattr(replay_helpers, "fresh_replay_state", AsyncMock(return_value=None))

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    handle_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_replay_item_treats_refreshed_failure_state_as_committed_after_commit_dbapi_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="processing",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    refreshed_item = SimpleNamespace(
        id=item.id,
        attempt_count=2,
        status="pending",
        details={
            "replay_failure": {
                "attempt_count": 2,
                "disposition": "retryable",
                "failed_at": "2026-03-23T08:55:00+00:00",
                "next_attempt_after": "2026-03-23T09:00:00+00:00",
            }
        },
        last_attempt_at=datetime(2026, 3, 23, 8, 55, tzinfo=UTC),
        processed_at=None,
        last_error="db down",
    )
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=OperationalError("commit", {}, Exception("drop")))
    session.get = AsyncMock(return_value=refreshed_item)
    monkeypatch.setattr(
        _task_maintenance,
        "_replay_one_degraded_item",
        AsyncMock(side_effect=OperationalError("select 1", {}, Exception("db down"))),
    )
    monkeypatch.setattr(
        replay_helpers, "persist_failure_state", AsyncMock(return_value=refreshed_item)
    )
    monkeypatch.setattr(
        replay_helpers,
        "serialize_replay_state",
        lambda *, item: {"state_source": "refreshed" if item is refreshed_item else "original"},
    )
    monkeypatch.setattr(
        replay_helpers,
        "fresh_replay_state",
        AsyncMock(return_value={"state_source": "refreshed"}),
    )

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 23, tzinfo=UTC),
    )

    assert had_error is True
    assert session.rollback.await_count == 2
    session.get.assert_awaited_once_with(LLMReplayQueueItem, item.id, with_for_update=True)


@pytest.mark.asyncio
async def test_process_replay_item_stops_commit_recovery_when_failure_state_cannot_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="done",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    refreshed_item = SimpleNamespace(id=item.id, attempt_count=2, status="pending")
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=OperationalError("commit", {}, Exception("drop")))
    session.get = AsyncMock(return_value=refreshed_item)
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(replay_helpers, "fresh_replay_state", AsyncMock(return_value=None))
    monkeypatch.setattr(replay_helpers, "persist_failure_state", AsyncMock(return_value=None))

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_process_replay_item_recovers_when_commit_confirmation_read_raises_dbapi_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="done",
        details={},
        last_attempt_at=None,
        processed_at=None,
        last_error=None,
    )
    refreshed_item = SimpleNamespace(id=item.id, attempt_count=2, status="pending")
    session = AsyncMock()
    session.commit = AsyncMock(
        side_effect=[OperationalError("commit", {}, Exception("drop")), None]
    )
    session.get = AsyncMock(return_value=refreshed_item)
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        replay_helpers,
        "fresh_replay_state",
        AsyncMock(side_effect=OperationalError("select 1", {}, Exception("db down"))),
    )
    monkeypatch.setattr(
        replay_helpers, "persist_failure_state", AsyncMock(return_value=refreshed_item)
    )

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 23, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.get.assert_awaited_once_with(LLMReplayQueueItem, item.id, with_for_update=True)
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_process_replay_item_does_not_clobber_new_replay_request_during_commit_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
        attempt_count=2,
        status="pending",
        details={"replay_request_id": str(uuid4())},
        last_attempt_at=None,
        processed_at=None,
        last_error="db down",
    )
    refreshed_item = SimpleNamespace(
        id=item.id,
        attempt_count=0,
        status="pending",
        details={"replay_request_id": str(uuid4())},
    )
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=OperationalError("commit", {}, Exception("drop")))
    session.get = AsyncMock(return_value=refreshed_item)
    monkeypatch.setattr(
        _task_maintenance, "_replay_one_degraded_item", AsyncMock(side_effect=ValueError("boom"))
    )
    monkeypatch.setattr(replay_helpers, "persist_failure_state", AsyncMock(return_value=item))
    monkeypatch.setattr(replay_helpers, "fresh_replay_state", AsyncMock(return_value=None))

    had_error = await _task_maintenance._process_replay_item(
        deps=SimpleNamespace(LLMReplayQueueItem=LLMReplayQueueItem),
        session=session,
        item=item,
        tier2=object(),
        pipeline=object(),
        trends=[],
        now=datetime(2026, 3, 23, tzinfo=UTC),
    )

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.get.assert_awaited_once_with(LLMReplayQueueItem, item.id, with_for_update=True)
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_replay_degraded_events_async_rolls_back_when_runtime_build_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = SimpleNamespace(
        id=uuid4(),
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
        SimpleNamespace(all=lambda: [item]),
    ]

    class _SessionContext:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    deps = SimpleNamespace(
        settings=SimpleNamespace(LLM_DEGRADED_MODE_ENABLED=False, LLM_TIER2_MODEL="tier2-model"),
        async_session_maker=lambda: _SessionContext(),
        select=select,
        LLMReplayQueueItem=LLMReplayQueueItem,
        Trend=Trend,
        Tier2Classifier=object,
        ProcessingPipeline=object,
        asyncio=SimpleNamespace(to_thread=AsyncMock()),
    )
    build_runtime = AsyncMock(side_effect=RuntimeError("runtime down"))
    monkeypatch.setattr(replay_helpers, "build_replay_runtime", build_runtime)

    with pytest.raises(RuntimeError, match="runtime down"):
        await _task_maintenance.replay_degraded_events_async(deps=deps, limit=1)

    build_runtime.assert_awaited_once_with(deps=deps, session=session)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_lineage_replay_status_returns_when_no_relevant_lineages() -> None:
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=list)

    await _task_maintenance._sync_lineage_replay_status(session=session, event_id=uuid4())

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_replay_status_reads_status_from_new_session() -> None:
    replay_item = SimpleNamespace(status="done")
    inner_session = AsyncMock()
    inner_session.get = AsyncMock(return_value=replay_item)

    class _SessionContext:
        async def __aenter__(self) -> AsyncMock:
            return inner_session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    status = await replay_helpers.fresh_replay_status(
        deps=SimpleNamespace(
            async_session_maker=lambda: _SessionContext(),
            LLMReplayQueueItem=LLMReplayQueueItem,
        ),
        item_id=uuid4(),
    )

    assert status == "done"


@pytest.mark.asyncio
async def test_fresh_replay_status_handles_missing_or_non_string_rows() -> None:
    missing_session = AsyncMock()
    missing_session.get = AsyncMock(return_value=None)
    non_string_session = AsyncMock()
    non_string_session.get = AsyncMock(return_value=SimpleNamespace(status=123))

    class _MissingContext:
        async def __aenter__(self) -> AsyncMock:
            return missing_session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class _NonStringContext:
        async def __aenter__(self) -> AsyncMock:
            return non_string_session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    missing_status = await replay_helpers.fresh_replay_status(
        deps=SimpleNamespace(
            async_session_maker=lambda: _MissingContext(),
            LLMReplayQueueItem=LLMReplayQueueItem,
        ),
        item_id=uuid4(),
    )
    non_string_status = await replay_helpers.fresh_replay_status(
        deps=SimpleNamespace(
            async_session_maker=lambda: _NonStringContext(),
            LLMReplayQueueItem=LLMReplayQueueItem,
        ),
        item_id=uuid4(),
    )

    assert missing_status is None
    assert non_string_status is None
