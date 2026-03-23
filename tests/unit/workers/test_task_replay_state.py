from __future__ import annotations

from datetime import UTC, datetime
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
    handle_failure = AsyncMock()
    monkeypatch.setattr(_task_maintenance, "_handle_replay_item_failure", handle_failure)
    monkeypatch.setattr(
        replay_helpers,
        "fresh_replay_state",
        AsyncMock(
            return_value={
                "status": "error",
                "attempt_count": 2,
                "last_attempt_at": None,
                "processed_at": None,
                "last_error": "Event not found",
                "replay_failure": {"disposition": "manual_review"},
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

    assert had_error is True
    session.rollback.assert_awaited_once()
    session.get.assert_not_awaited()
    handle_failure.assert_awaited_once()


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
    refreshed_item = SimpleNamespace(id=item.id, attempt_count=2)
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
    session.get.assert_awaited_with(LLMReplayQueueItem, item.id)
    handle_failure.assert_awaited_once()


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
    session.get.assert_awaited_with(LLMReplayQueueItem, item.id)


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
