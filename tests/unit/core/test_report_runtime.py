from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
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
async def test_load_active_trend_input_ids_returns_empty_for_missing_trend_id() -> None:
    session = AsyncMock()

    evidence_ids, event_ids = await report_runtime._load_active_trend_input_ids(
        session=session,
        trend_id=None,
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


@pytest.mark.asyncio
async def test_build_report_generation_manifest_records_live_state_inputs() -> None:
    period_evidence_id = uuid4()
    period_event_id = uuid4()
    live_evidence_id = uuid4()
    live_event_id = uuid4()

    class _Rows:
        def __init__(self, rows: list[tuple[object, object]]) -> None:
            self._rows = rows

        def all(self) -> list[tuple[object, object]]:
            return self._rows

    session = AsyncMock()
    session.execute.side_effect = [
        _Rows([(period_evidence_id, period_event_id)]),
        _Rows([(period_evidence_id, period_event_id), (live_evidence_id, live_event_id)]),
    ]

    manifest = await report_runtime.build_report_generation_manifest(
        session=session,
        trend=SimpleNamespace(
            id=uuid4(),
            runtime_trend_id="trend-runtime",
            definition={"id": "trend-runtime"},
        ),
        period_start=datetime(2026, 3, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 8, tzinfo=UTC),
        report_type="weekly",
        top_events=[],
        narrative=report_runtime.NarrativeResult(
            narrative="narrative",
            grounding_status="grounded",
            grounding_violation_count=0,
        ),
    )

    assert manifest["inputs"]["evidence_ids"] == [str(period_evidence_id)]
    assert manifest["inputs"]["event_ids"] == [str(period_event_id)]
    assert manifest["inputs"]["live_state_evidence_ids"] == [
        str(period_evidence_id),
        str(live_evidence_id),
    ]
    assert manifest["inputs"]["live_state_event_ids"] == sorted(
        [str(period_event_id), str(live_event_id)]
    )
    assert manifest["inputs"]["counts"]["live_state_evidence"] == 2
    assert manifest["inputs"]["counts"]["live_state_events"] == 2
