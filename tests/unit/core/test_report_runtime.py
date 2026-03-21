from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core import report_runtime

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_load_report_input_ids_returns_empty_for_missing_trend_id() -> None:
    session = AsyncMock()

    evidence_ids, event_ids = await report_runtime._load_report_input_ids(
        session=session,
        trend_id=None,
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 8, tzinfo=UTC),
    )

    assert evidence_ids == []
    assert event_ids == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_load_report_input_ids_supports_async_all_results() -> None:
    evidence_id = uuid4()
    event_id = uuid4()

    class _AsyncRows:
        async def all(self) -> list[tuple[object, object]]:
            return [(evidence_id, event_id), (uuid4(), None)]

    session = AsyncMock()
    session.execute.return_value = _AsyncRows()

    evidence_ids, event_ids = await report_runtime._load_report_input_ids(
        session=session,
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 8, tzinfo=UTC),
    )

    assert evidence_ids[0] == str(evidence_id)
    assert event_ids == [str(event_id)]


@pytest.mark.asyncio
async def test_load_report_input_ids_supports_sync_all_results() -> None:
    evidence_id = uuid4()
    event_id = uuid4()

    class _Rows:
        def all(self) -> list[tuple[object, object]]:
            return [(evidence_id, event_id)]

    session = AsyncMock()
    session.execute.return_value = _Rows()

    evidence_ids, event_ids = await report_runtime._load_report_input_ids(
        session=session,
        trend_id=uuid4(),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 8, tzinfo=UTC),
    )

    assert evidence_ids == [str(evidence_id)]
    assert event_ids == [str(event_id)]
