from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.core.config import settings
from src.processing import cost_tracker as cost_tracker_module
from src.processing.cost_tracker import TIER1, BudgetExceededError, CostTracker
from src.storage.models import ApiUsage

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_check_budget_blocks_when_tier_call_limit_reached(
    mock_db_session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 2)
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=2,
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=0.1,
    )
    mock_db_session.scalar.side_effect = [usage, Decimal("0.1")]
    tracker = CostTracker(session=mock_db_session)

    allowed, reason = await tracker.check_budget(TIER1)

    assert allowed is False
    assert reason is not None
    assert "daily call limit" in reason


@pytest.mark.asyncio
async def test_check_budget_blocks_when_daily_cost_limit_reached(
    mock_db_session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 100)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 1.0)
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=1,
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=0.2,
    )
    mock_db_session.scalar.side_effect = [usage, Decimal("1.0")]
    tracker = CostTracker(session=mock_db_session)

    allowed, reason = await tracker.check_budget(TIER1)

    assert allowed is False
    assert reason is not None
    assert "daily cost limit" in reason


@pytest.mark.asyncio
async def test_record_usage_updates_counters_and_cost(mock_db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 10.0)
    monkeypatch.setattr(settings, "COST_ALERT_THRESHOLD_PCT", 80)
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=0,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0,
    )
    mock_db_session.scalar.side_effect = [usage, Decimal("0.3")]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [usage])
    tracker = CostTracker(session=mock_db_session)

    await tracker.record_usage(tier=TIER1, input_tokens=1_000_000, output_tokens=500_000)

    assert usage.call_count == 1
    assert usage.input_tokens == 1_000_000
    assert usage.output_tokens == 500_000
    assert float(usage.estimated_cost_usd) == pytest.approx(0.3)
    assert mock_db_session.flush.await_count >= 1


@pytest.mark.asyncio
async def test_record_usage_denies_when_call_limit_reached(mock_db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 1)
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=1,
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=0.1,
    )
    mock_db_session.scalar.return_value = usage
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [usage])
    budget_denials: list[tuple[str, str]] = []
    monkeypatch.setattr(
        cost_tracker_module,
        "record_budget_denial",
        lambda *, tier, reason: budget_denials.append((tier, reason)),
    )
    tracker = CostTracker(session=mock_db_session)

    with pytest.raises(BudgetExceededError, match="daily call limit"):
        await tracker.record_usage(tier=TIER1, input_tokens=1000, output_tokens=100)

    assert usage.call_count == 1
    assert budget_denials == [(TIER1, "daily_call_limit")]


@pytest.mark.asyncio
async def test_get_daily_summary_marks_sleep_mode_when_limit_reached(
    mock_db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 2)
    monkeypatch.setattr(settings, "TIER2_MAX_DAILY_CALLS", 200)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_DAILY_CALLS", 500)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 5.0)
    today = datetime.now(tz=UTC).date()

    rows = [
        ApiUsage(
            usage_date=today,
            tier="tier1",
            call_count=2,
            input_tokens=2000,
            output_tokens=500,
            estimated_cost_usd=0.12,
        ),
    ]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: rows)
    tracker = CostTracker(session=mock_db_session)

    summary = await tracker.get_daily_summary()

    assert summary["status"] == "sleep_mode"
    assert summary["tiers"]["tier1"]["calls"] == 2
    assert summary["tiers"]["tier1"]["call_limit"] == 2
