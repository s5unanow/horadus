from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.core.trend_engine import TrendEngine
from src.core.trend_restatement import build_trend_projection_check
from src.storage.database import async_session_maker
from src.storage.models import Trend
from src.storage.trend_state_models import TrendStateVersion
from tests.integration.test_trend_engine_concurrency import (
    _create_trend_and_events,
    _sample_factors,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_evidence_applies_accrued_decay_before_new_delta() -> None:
    old_boundary = datetime.now(tz=UTC) - timedelta(days=30)
    trend_id, event_id, _event_two_id, claim_id, _claim_two_id = await _create_trend_and_events(
        current_log_odds=1.0,
        updated_at=old_boundary,
    )
    async with async_session_maker() as session:
        trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))
        assert trend is not None
        state = await session.get(TrendStateVersion, trend.active_state_version_id)
        assert state is not None
        trend.updated_at = trend.last_decayed_at = old_boundary
        state.activated_at = old_boundary
        await session.commit()

    async with async_session_maker() as session:
        trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))
        assert trend is not None
        await TrendEngine(session=session).apply_evidence(
            trend=trend,
            delta=0.2,
            event_id=event_id,
            event_claim_id=claim_id,
            signal_type="fresh_signal",
            factors=_sample_factors(),
            reasoning="decay clock integration test",
        )
        await session.commit()

    async with async_session_maker() as session:
        trend = await session.scalar(select(Trend).where(Trend.id == trend_id).limit(1))
        assert trend is not None
        projection = await build_trend_projection_check(session=session, trend=trend)

    assert float(trend.current_log_odds) == pytest.approx(0.7, rel=1e-5)
    assert projection.matches_projection is True
