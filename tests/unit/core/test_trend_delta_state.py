from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.trend_delta_state import apply_locked_trend_delta, resolve_trend_decay_clock

pytestmark = pytest.mark.unit


def test_resolve_trend_decay_clock_normalizes_legacy_naive_timestamp() -> None:
    naive = datetime(2026, 7, 26, tzinfo=UTC).replace(tzinfo=None)
    trend = SimpleNamespace(last_decayed_at=None, updated_at=naive)

    assert resolve_trend_decay_clock(trend) == naive.replace(tzinfo=UTC)


def _locked_result(*, current: float, baseline: float, last_decayed_at: datetime):
    result = MagicMock()
    result.one_or_none.return_value = SimpleNamespace(
        _mapping={
            "current_log_odds": current,
            "baseline_log_odds": baseline,
            "last_decayed_at": last_decayed_at,
            "decay_half_life_days": 30,
        }
    )
    return result


@pytest.mark.asyncio
async def test_locked_delta_handles_persisted_and_fallback_paths() -> None:
    applied_at = datetime.now(UTC)
    locked = _locked_result(current=1.0, baseline=0.0, last_decayed_at=applied_at)
    updated = MagicMock()
    updated.scalar_one_or_none.return_value = 1.2
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[locked, updated])

    previous, current, effective_at = await apply_locked_trend_delta(
        session=session,
        trend_id=uuid4(),
        delta=0.2,
        reason="test",
        requested_at=applied_at,
        active_state_version_id=None,
        trend_name="Trend",
        fallback_current_log_odds=0.8,
    )

    assert (previous, current, effective_at) == pytest.approx((1.0, 1.2, applied_at))

    locked.one_or_none.return_value = None
    session.execute = AsyncMock(return_value=locked)
    previous, current, _effective_at = await apply_locked_trend_delta(
        session=session,
        trend_id=uuid4(),
        delta=0.2,
        reason="test",
        requested_at=applied_at,
        active_state_version_id=None,
        trend_name=None,
        fallback_current_log_odds=0.8,
    )
    assert (previous, current) == pytest.approx((0.8, 1.0))

    with pytest.raises(ValueError, match="not found"):
        await apply_locked_trend_delta(
            session=session,
            trend_id=uuid4(),
            delta=0.2,
            reason="test",
            requested_at=applied_at,
            active_state_version_id=None,
            trend_name=None,
            fallback_current_log_odds=None,
        )


@pytest.mark.asyncio
async def test_locked_delta_awaits_driver_results() -> None:
    applied_at = datetime.now(UTC)

    async def locked_row():
        return _locked_result(
            current=1.0,
            baseline=0.0,
            last_decayed_at=applied_at,
        ).one_or_none()

    async def updated_value():
        return 1.2

    locked = MagicMock()
    locked.one_or_none.return_value = locked_row()
    updated = MagicMock()
    updated.scalar_one_or_none.return_value = updated_value()
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[locked, updated])

    previous, current, _effective_at = await apply_locked_trend_delta(
        session=session,
        trend_id=uuid4(),
        delta=0.2,
        reason="test",
        requested_at=applied_at,
        active_state_version_id=None,
        trend_name=None,
        fallback_current_log_odds=0.8,
    )

    assert (previous, current) == pytest.approx((1.0, 1.2))


@pytest.mark.asyncio
async def test_locked_delta_applies_accrued_decay_before_new_delta() -> None:
    applied_at = datetime.now(UTC)
    locked = _locked_result(
        current=1.0,
        baseline=0.0,
        last_decayed_at=applied_at - timedelta(days=30),
    )
    updated = MagicMock()
    updated.scalar_one_or_none.return_value = 0.7
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[locked, updated])

    previous, current, effective_at = await apply_locked_trend_delta(
        session=session,
        trend_id=uuid4(),
        delta=0.2,
        reason="test",
        requested_at=applied_at,
        active_state_version_id=None,
        trend_name=None,
        fallback_current_log_odds=None,
    )

    assert (previous, current) == pytest.approx((0.5, 0.7))
    assert effective_at == applied_at
    update_params = session.execute.await_args_list[1].args[0].compile().params
    assert update_params["current_log_odds"] == Decimal("0.7")
    assert update_params["last_decayed_at"] == applied_at


@pytest.mark.asyncio
async def test_locked_delta_fails_if_locked_row_disappears() -> None:
    applied_at = datetime.now(UTC)
    locked = _locked_result(current=1.0, baseline=0.0, last_decayed_at=applied_at)
    updated = MagicMock()
    updated.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[locked, updated])

    with pytest.raises(RuntimeError, match="disappeared"):
        await apply_locked_trend_delta(
            session=session,
            trend_id=uuid4(),
            delta=0.2,
            reason="test",
            requested_at=applied_at,
            active_state_version_id=None,
            trend_name=None,
            fallback_current_log_odds=None,
        )


@pytest.mark.asyncio
async def test_locked_delta_updates_active_state_version() -> None:
    applied_at = datetime.now(UTC)
    locked = _locked_result(current=1.0, baseline=0.0, last_decayed_at=applied_at)
    updated = MagicMock()
    updated.scalar_one_or_none.return_value = 1.2
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[locked, updated, MagicMock()])

    previous, current, _effective_at = await apply_locked_trend_delta(
        session=session,
        trend_id=uuid4(),
        delta=0.2,
        reason="test",
        requested_at=applied_at,
        active_state_version_id=uuid4(),
        trend_name=None,
        fallback_current_log_odds=None,
    )

    assert (previous, current) == pytest.approx((1.0, 1.2))
    assert "trend_state_versions" in str(session.execute.await_args_list[2].args[0])
