from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.processing.event_lineage as event_lineage
import src.processing.event_lineage_invalidation as lineage_invalidation
from src.storage.models import Event, Trend, TrendEvidence

pytestmark = pytest.mark.unit


def _evidence(*, trend_id=None, event_id=None) -> TrendEvidence:
    return TrendEvidence(
        id=uuid4(),
        trend_id=trend_id or uuid4(),
        event_id=event_id or uuid4(),
        event_claim_id=uuid4(),
        signal_type="signal",
        delta_log_odds=Decimal("0.2"),
        is_invalidated=False,
    )


@pytest.mark.asyncio
async def test_claim_lineage_evidence_invalidation_updates_claimed_row() -> None:
    evidence = _evidence()
    invalidated_at = datetime.now(tz=UTC)
    result = MagicMock()
    result.scalar_one_or_none.return_value = evidence.id
    session = AsyncMock()
    session.execute.return_value = result

    claimed = await lineage_invalidation.claim_evidence_invalidation(
        session, evidence, invalidated_at
    )

    assert claimed is True
    assert evidence.is_invalidated is True
    assert evidence.invalidated_at == invalidated_at


@pytest.mark.asyncio
async def test_claim_lineage_evidence_invalidation_preserves_lost_row() -> None:
    evidence = _evidence()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute.return_value = result

    claimed = await lineage_invalidation.claim_evidence_invalidation(
        session, evidence, datetime.now(tz=UTC)
    )

    assert claimed is False
    assert evidence.is_invalidated is False
    assert evidence.invalidated_at is None


@pytest.mark.asyncio
async def test_claim_lineage_evidence_invalidation_accepts_async_test_result() -> None:
    evidence = _evidence()
    result = MagicMock()
    result.scalar_one_or_none = AsyncMock(return_value=evidence.id)
    session = AsyncMock()
    session.execute.return_value = result

    claimed = await lineage_invalidation.claim_evidence_invalidation(
        session, evidence, datetime.now(tz=UTC)
    )

    assert claimed is True


@pytest.mark.asyncio
async def test_claim_evidence_invalidations_returns_only_winners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _evidence(), _evidence()
    claim = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(lineage_invalidation, "claim_evidence_invalidation", claim)

    winners = await lineage_invalidation.claim_evidence_invalidations(
        AsyncMock(),
        [first, second],
        datetime.now(tz=UTC),
    )

    assert winners == [first]
    assert claim.await_count == 2


@pytest.mark.asyncio
async def test_repair_compensates_only_claimed_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    trend = Trend(id=uuid4(), name="Trend", current_log_odds=-2.0)
    claimed_evidence = _evidence(trend_id=trend.id, event_id=event_id)
    lost_evidence = _evidence(trend_id=trend.id, event_id=event_id)
    session = AsyncMock()
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [claimed_evidence, lost_evidence]),
        SimpleNamespace(all=lambda: [trend]),
    ]
    claim = AsyncMock(return_value=[claimed_evidence])
    compensate = AsyncMock()
    replay_id = uuid4()
    monkeypatch.setattr(event_lineage, "claim_evidence_invalidations", claim)
    monkeypatch.setattr(
        event_lineage,
        "_load_prior_compensation_by_evidence_id",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(event_lineage, "apply_compensating_restatement", compensate)
    monkeypatch.setattr(
        event_lineage,
        "_enqueue_event_replay",
        AsyncMock(return_value=replay_id),
    )

    result = await event_lineage._repair_affected_events(
        session=session,
        events=[Event(id=event_id)],
        reason="split",
    )

    claim.assert_awaited_once()
    compensate.assert_awaited_once()
    assert result == ((claimed_evidence.id,), (event_id,), (replay_id,))
