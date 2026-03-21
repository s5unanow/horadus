from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.workers import _task_maintenance

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_replay_one_degraded_item_passes_provenance_derivation() -> None:
    event = SimpleNamespace(id="event-1")
    item = SimpleNamespace(
        id="queue-1",
        event_id="event-1",
        details={"original_extraction_provenance": {"stage": "tier2"}},
        status="pending",
        processed_at=None,
        locked_at="locked",
        locked_by="worker",
        last_error="old",
    )
    session = AsyncMock()
    session.get.return_value = event
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
        "queue_item_id": "queue-1",
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
