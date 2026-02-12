from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from src.core.config import settings
from src.core.observability import LLM_BUDGET_DENIALS_TOTAL
from src.processing.cost_tracker import TIER1, BudgetExceededError, CostTracker
from src.storage.database import async_session_maker
from src.storage.models import ApiUsage

pytestmark = pytest.mark.integration


async def _clear_today_usage() -> None:
    today = datetime.now(tz=UTC).date()
    async with async_session_maker() as session:
        await session.execute(delete(ApiUsage).where(ApiUsage.usage_date == today))
        await session.commit()


async def _attempt_record_usage(
    *,
    start_event: asyncio.Event,
    input_tokens: int,
    output_tokens: int,
) -> bool:
    async with async_session_maker() as session:
        tracker = CostTracker(session=session)
        await start_event.wait()
        try:
            await tracker.record_usage(
                tier=TIER1,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            await session.commit()
            return True
        except BudgetExceededError:
            await session.rollback()
            return False


@pytest.mark.asyncio
async def test_record_usage_blocks_call_limit_overshoot_under_concurrency(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 1)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 100.0)
    await _clear_today_usage()
    metric_before = LLM_BUDGET_DENIALS_TOTAL.labels(
        tier=TIER1,
        reason="daily_call_limit",
    )._value.get()

    start_event = asyncio.Event()
    tasks = [
        asyncio.create_task(
            _attempt_record_usage(
                start_event=start_event,
                input_tokens=1_000,
                output_tokens=100,
            )
        ),
        asyncio.create_task(
            _attempt_record_usage(
                start_event=start_event,
                input_tokens=1_000,
                output_tokens=100,
            )
        ),
    ]

    await asyncio.sleep(0.05)
    start_event.set()
    results = await asyncio.gather(*tasks)

    assert results.count(True) == 1
    assert results.count(False) == 1

    today = datetime.now(tz=UTC).date()
    async with async_session_maker() as session:
        row = await session.scalar(
            select(ApiUsage)
            .where(ApiUsage.usage_date == today)
            .where(ApiUsage.tier == TIER1)
            .limit(1)
        )
    assert row is not None
    assert row.call_count == 1

    metric_after = LLM_BUDGET_DENIALS_TOTAL.labels(
        tier=TIER1,
        reason="daily_call_limit",
    )._value.get()
    assert metric_after == metric_before + 1


@pytest.mark.asyncio
async def test_record_usage_blocks_cost_limit_overshoot_under_concurrency(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 10)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 0.00015)
    await _clear_today_usage()
    metric_before = LLM_BUDGET_DENIALS_TOTAL.labels(
        tier=TIER1,
        reason="daily_cost_limit",
    )._value.get()

    start_event = asyncio.Event()
    tasks = [
        asyncio.create_task(
            _attempt_record_usage(
                start_event=start_event,
                input_tokens=1_000,
                output_tokens=0,
            )
        ),
        asyncio.create_task(
            _attempt_record_usage(
                start_event=start_event,
                input_tokens=1_000,
                output_tokens=0,
            )
        ),
    ]

    await asyncio.sleep(0.05)
    start_event.set()
    results = await asyncio.gather(*tasks)

    assert results.count(True) == 1
    assert results.count(False) == 1

    today = datetime.now(tz=UTC).date()
    async with async_session_maker() as session:
        row = await session.scalar(
            select(ApiUsage)
            .where(ApiUsage.usage_date == today)
            .where(ApiUsage.tier == TIER1)
            .limit(1)
        )
    assert row is not None
    assert row.call_count == 1
    assert float(row.estimated_cost_usd) == pytest.approx(0.0001, abs=1e-8)

    metric_after = LLM_BUDGET_DENIALS_TOTAL.labels(
        tier=TIER1,
        reason="daily_cost_limit",
    )._value.get()
    assert metric_after == metric_before + 1
