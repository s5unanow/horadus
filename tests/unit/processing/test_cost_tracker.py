from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.processing import cost_tracker as cost_tracker_module
from src.processing.cost_tracker import EMBEDDING, TIER1, TIER2, BudgetExceededError, CostTracker
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


@pytest.mark.asyncio
async def test_get_tier_budget_snapshot_reports_remaining_capacity(
    mock_db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "TIER2_MAX_DAILY_CALLS", 10)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 2.0)
    today = datetime.now(tz=UTC).date()
    rows = [
        ApiUsage(
            usage_date=today,
            tier="tier2",
            call_count=4,
            input_tokens=4000,
            output_tokens=1000,
            estimated_cost_usd=0.8,
        ),
    ]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: rows)
    tracker = CostTracker(session=mock_db_session)

    snapshot = await tracker.get_tier_budget_snapshot(TIER2)

    assert snapshot.remaining_calls == 6
    assert snapshot.average_cost_per_call_usd == pytest.approx(0.2)
    assert snapshot.headroom_ratio == pytest.approx(0.6)
    assert snapshot.estimated_remaining_calls_from_budget == 6


@pytest.mark.asyncio
async def test_record_usage_uses_provider_model_pricing(mock_db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 10.0)
    monkeypatch.setattr(
        settings,
        "LLM_TOKEN_PRICING_USD_PER_1M",
        {"openai:gpt-4.1-mini": (1.0, 2.0)},
    )
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=0,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0,
    )
    mock_db_session.scalar.side_effect = [usage, Decimal("0")]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [usage])
    tracker = CostTracker(session=mock_db_session)

    await tracker.record_usage(
        tier=TIER1,
        input_tokens=1_000,
        output_tokens=500,
        provider="openai",
        model="gpt-4.1-mini",
    )

    assert float(usage.estimated_cost_usd) == pytest.approx(0.002)


@pytest.mark.asyncio
async def test_ensure_within_budget_fails_closed_for_missing_pricing(
    mock_db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "LLM_TOKEN_PRICING_USD_PER_1M",
        {"openai:gpt-4.1-mini": (0.4, 1.6)},
    )
    tracker = CostTracker(session=mock_db_session)

    with pytest.raises(BudgetExceededError, match="No token pricing configured"):
        await tracker.ensure_within_budget(
            TIER1,
            provider="openai",
            model="gpt-4.1-nano",
        )


@pytest.mark.asyncio
async def test_ensure_within_budget_returns_when_budget_allows_call(mock_db_session) -> None:
    tracker = CostTracker(session=mock_db_session)
    tracker.check_budget = AsyncMock(return_value=(True, None))

    await tracker.ensure_within_budget(TIER1)

    tracker.check_budget.assert_awaited_once_with(TIER1)


@pytest.mark.asyncio
async def test_ensure_within_budget_denies_with_default_message(
    mock_db_session, monkeypatch
) -> None:
    budget_denials: list[tuple[str, str, str | None]] = []

    def resolve_token_rates(_self: CostTracker, **_: object) -> tuple[Decimal, Decimal]:
        return (Decimal("0.1"), Decimal("0.2"))

    monkeypatch.setattr(
        CostTracker,
        "_resolve_token_rates",
        resolve_token_rates,
    )

    def capture_denial(
        self,
        *,
        tier: str,
        reason_code: str,
        reason_detail: str | None,
        projected_total_cost: Decimal | None = None,
        daily_limit: Decimal | None = None,
    ) -> None:
        _ = projected_total_cost, daily_limit
        budget_denials.append((tier, reason_code, reason_detail))

    monkeypatch.setattr(CostTracker, "_log_budget_denial", capture_denial)
    tracker = CostTracker(session=mock_db_session)
    tracker.check_budget = AsyncMock(return_value=(False, None))

    with pytest.raises(BudgetExceededError, match="tier1 budget exceeded"):
        await tracker.ensure_within_budget(TIER1)

    assert budget_denials == [(TIER1, "budget_denied", None)]


@pytest.mark.asyncio
async def test_check_budget_allows_call_when_under_limits(mock_db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 10)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 5.0)
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=1,
        input_tokens=50,
        output_tokens=20,
        estimated_cost_usd=0.1,
    )
    mock_db_session.scalar.side_effect = [usage, Decimal("0.2")]
    tracker = CostTracker(session=mock_db_session)

    assert await tracker.check_budget(" Tier1 ") == (True, None)


@pytest.mark.asyncio
async def test_record_usage_denies_when_daily_cost_limit_would_be_exceeded(
    mock_db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 0.2)
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=0,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0,
    )
    other_usage = ApiUsage(
        usage_date=today,
        tier=TIER2,
        call_count=1,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0.19,
    )
    mock_db_session.scalar.return_value = usage
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [usage, other_usage])
    denials: list[dict[str, object]] = []

    def capture_denial(
        self,
        *,
        tier: str,
        reason_code: str,
        reason_detail: str | None,
        projected_total_cost: Decimal | None = None,
        daily_limit: Decimal | None = None,
    ) -> None:
        denials.append(
            {
                "tier": tier,
                "reason_code": reason_code,
                "reason_detail": reason_detail,
                "projected_total_cost": projected_total_cost,
                "daily_limit": daily_limit,
            }
        )

    monkeypatch.setattr(CostTracker, "_log_budget_denial", capture_denial)
    tracker = CostTracker(session=mock_db_session)

    with pytest.raises(BudgetExceededError, match="daily cost limit"):
        await tracker.record_usage(tier=TIER1, input_tokens=1_000_000, output_tokens=0)

    assert denials[0]["reason_code"] == "daily_cost_limit"
    assert denials[0]["projected_total_cost"] is not None


@pytest.mark.asyncio
async def test_get_daily_summary_reports_active_mode_without_budget_limit(
    mock_db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "TIER1_MAX_DAILY_CALLS", 2)
    monkeypatch.setattr(settings, "TIER2_MAX_DAILY_CALLS", 3)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_DAILY_CALLS", 4)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 0.0)
    today = datetime.now(tz=UTC).date()
    rows = [
        ApiUsage(
            usage_date=today,
            tier=TIER1,
            call_count=1,
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.5,
        )
    ]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: rows)
    tracker = CostTracker(session=mock_db_session)

    summary = await tracker.get_daily_summary()

    assert summary["status"] == "active"
    assert summary["budget_remaining_usd"] is None
    assert summary["tiers"][EMBEDDING]["calls"] == 0


@pytest.mark.asyncio
async def test_get_or_create_usage_creates_new_row(mock_db_session) -> None:
    today = datetime.now(tz=UTC).date()
    mock_db_session.scalar.return_value = None

    @asynccontextmanager
    async def nested_transaction():
        yield

    mock_db_session.begin_nested.side_effect = nested_transaction
    tracker = CostTracker(session=mock_db_session)

    usage = await tracker._get_or_create_usage(today, TIER1)

    assert usage.usage_date == today
    assert usage.tier == TIER1
    mock_db_session.add.assert_called_once()
    assert mock_db_session.flush.await_count == 1


@pytest.mark.asyncio
async def test_get_or_create_usage_recovers_from_integrity_error(mock_db_session) -> None:
    today = datetime.now(tz=UTC).date()
    existing = ApiUsage(
        usage_date=today,
        tier=TIER1,
        call_count=0,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0,
    )
    mock_db_session.scalar.side_effect = [None, existing]

    @asynccontextmanager
    async def nested_transaction():
        raise cost_tracker_module.IntegrityError("stmt", "params", "orig")
        yield

    mock_db_session.begin_nested.side_effect = nested_transaction
    tracker = CostTracker(session=mock_db_session)

    usage = await tracker._get_or_create_usage(today, TIER1)

    assert usage is existing


@pytest.mark.asyncio
async def test_get_or_create_usage_raises_when_row_still_missing(mock_db_session) -> None:
    today = datetime.now(tz=UTC).date()
    mock_db_session.scalar.side_effect = [None, None]

    @asynccontextmanager
    async def nested_transaction():
        raise cost_tracker_module.IntegrityError("stmt", "params", "orig")
        yield

    mock_db_session.begin_nested.side_effect = nested_transaction
    tracker = CostTracker(session=mock_db_session)

    with pytest.raises(RuntimeError, match="Failed to create or load api_usage row"):
        await tracker._get_or_create_usage(today, TIER1)


@pytest.mark.asyncio
async def test_load_usage_rows_for_date_optionally_locks_rows(mock_db_session) -> None:
    today = datetime.now(tz=UTC).date()
    rows = [SimpleNamespace(tier=TIER1)]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: rows)
    tracker = CostTracker(session=mock_db_session)

    assert await tracker._load_usage_rows_for_date(today, for_update=False) == rows
    assert "FOR UPDATE" not in str(mock_db_session.scalars.await_args_list[0].args[0])

    await tracker._load_usage_rows_for_date(today, for_update=True)
    assert "FOR UPDATE" in str(mock_db_session.scalars.await_args_list[1].args[0])


@pytest.mark.asyncio
async def test_total_cost_for_date_returns_decimal(mock_db_session) -> None:
    mock_db_session.scalar.return_value = 1.25
    tracker = CostTracker(session=mock_db_session)

    assert await tracker._total_cost_for_date(datetime.now(tz=UTC).date()) == Decimal("1.25")


@pytest.mark.asyncio
async def test_maybe_log_alert_respects_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = CostTracker(session=SimpleNamespace())
    log_calls: list[dict[str, object]] = []

    def log_warning(event: str, **kwargs: object) -> None:
        log_calls.append({"event": event, **kwargs})

    monkeypatch.setattr(cost_tracker_module.logger, "warning", log_warning)
    usage_date = datetime.now(tz=UTC).date()

    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 0.0)
    monkeypatch.setattr(settings, "COST_ALERT_THRESHOLD_PCT", 80)
    await tracker._maybe_log_alert(usage_date)

    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 10.0)
    monkeypatch.setattr(settings, "COST_ALERT_THRESHOLD_PCT", 0)
    await tracker._maybe_log_alert(usage_date)

    monkeypatch.setattr(settings, "COST_ALERT_THRESHOLD_PCT", 80)
    tracker._total_cost_for_date = AsyncMock(side_effect=[Decimal("7.0"), Decimal("8.5")])
    await tracker._maybe_log_alert(usage_date)
    await tracker._maybe_log_alert(usage_date)

    assert len(log_calls) == 1
    assert log_calls[0]["event"] == "Daily LLM cost alert threshold reached"


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (" tier1 ", TIER1),
        ("TIER2", TIER2),
        ("embedding", EMBEDDING),
    ],
)
def test_normalize_tier_accepts_known_values(tier: str, expected: str) -> None:
    assert CostTracker._normalize_tier(tier) == expected


def test_normalize_tier_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unsupported cost tracker tier"):
        CostTracker._normalize_tier("invalid")


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("daily call limit (2) exceeded", "daily_call_limit"),
        ("daily cost limit ($1.0) exceeded", "daily_cost_limit"),
        ("invalid pricing config", "invalid_pricing_config"),
        (None, "budget_denied"),
    ],
)
def test_denial_reason_code_maps_messages(reason: str | None, expected: str) -> None:
    assert CostTracker._denial_reason_code(reason) == expected


def test_default_provider_model_for_tier_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PRIMARY_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_TIER1_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "LLM_TIER2_MODEL", "gpt-4.1")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")

    assert CostTracker._default_provider_model_for_tier(TIER1) == ("openai", "gpt-4.1-mini")
    assert CostTracker._default_provider_model_for_tier(TIER2) == ("openai", "gpt-4.1")
    assert CostTracker._default_provider_model_for_tier(EMBEDDING) == (
        "openai",
        "text-embedding-3-small",
    )


def test_default_provider_model_for_tier_rejects_unknown_tier() -> None:
    with pytest.raises(ValueError, match="Unsupported cost tracker tier"):
        CostTracker._default_provider_model_for_tier("invalid")


def test_resolve_token_rates_uses_defaults_and_normalizes_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PRIMARY_PROVIDER", "OpenAI")
    monkeypatch.setattr(settings, "LLM_TIER1_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr(
        settings,
        "LLM_TOKEN_PRICING_USD_PER_1M",
        {"openai:gpt-4.1-mini": (0.4, 1.6)},
    )
    tracker = CostTracker(session=SimpleNamespace())

    input_rate, output_rate = tracker._resolve_token_rates(
        tier=TIER1,
        provider=" OpenAI ",
        model=None,
    )

    assert input_rate == Decimal("0.4")
    assert output_rate == Decimal("1.6")


def test_log_budget_denial_records_metric_and_structured_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[str, str]] = []
    log_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        cost_tracker_module,
        "record_budget_denial",
        lambda *, tier, reason: recorded.append((tier, reason)),
    )
    monkeypatch.setattr(
        cost_tracker_module.logger,
        "warning",
        lambda event, **kwargs: log_calls.append({"event": event, **kwargs}),
    )
    tracker = CostTracker(session=SimpleNamespace())

    tracker._log_budget_denial(
        tier=TIER1,
        reason_code="daily_cost_limit",
        reason_detail="daily cost limit exceeded",
        projected_total_cost=Decimal("1.25"),
        daily_limit=Decimal("1.0"),
    )

    assert recorded == [(TIER1, "daily_cost_limit")]
    assert log_calls[0]["event"] == "LLM budget enforcement denied request"
    assert log_calls[0]["projected_total_cost_usd"] == 1.25
