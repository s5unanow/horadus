"""
Cost tracking and budget enforcement for LLM usage.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.storage.models import ApiUsage

logger = structlog.get_logger(__name__)

TIER1 = "tier1"
TIER2 = "tier2"
EMBEDDING = "embedding"

KNOWN_TIERS = (TIER1, TIER2, EMBEDDING)

COST_PER_1M_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    TIER1: (Decimal("0.10"), Decimal("0.40")),
    TIER2: (Decimal("0.15"), Decimal("0.60")),
    EMBEDDING: (Decimal("0.10"), Decimal("0.00")),
}


class BudgetExceededError(RuntimeError):
    """Raised when an LLM call would exceed configured daily budget."""


class CostTracker:
    """Track per-tier LLM usage and enforce daily cost/call limits."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_within_budget(self, tier: str) -> None:
        """Raise BudgetExceededError if the requested tier budget is exhausted."""
        allowed, reason = await self.check_budget(tier)
        if allowed:
            return
        msg = reason or f"{tier} budget exceeded"
        raise BudgetExceededError(msg)

    async def check_budget(self, tier: str) -> tuple[bool, str | None]:
        """Return whether a tier can make another call right now."""
        normalized_tier = self._normalize_tier(tier)
        today = datetime.now(tz=UTC).date()
        usage = await self._get_or_create_usage(today, normalized_tier)

        call_limit = self._call_limit_for_tier(normalized_tier)
        if call_limit > 0 and usage.call_count >= call_limit:
            return (
                False,
                f"{normalized_tier} daily call limit ({call_limit}) exceeded",
            )

        total_cost = await self._total_cost_for_date(today)
        daily_limit = Decimal(str(settings.DAILY_COST_LIMIT_USD))
        if daily_limit > 0 and total_cost >= daily_limit:
            return (
                False,
                f"daily cost limit (${settings.DAILY_COST_LIMIT_USD}) exceeded",
            )

        return (True, None)

    async def record_usage(
        self,
        *,
        tier: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Persist token and cost counters for one successful API call."""
        normalized_tier = self._normalize_tier(tier)
        today = datetime.now(tz=UTC).date()
        usage = await self._get_or_create_usage(today, normalized_tier)

        safe_input_tokens = max(0, int(input_tokens))
        safe_output_tokens = max(0, int(output_tokens))
        input_rate, output_rate = COST_PER_1M_TOKENS.get(
            normalized_tier,
            (Decimal("0"), Decimal("0")),
        )
        estimated_cost = (Decimal(safe_input_tokens) / Decimal(1_000_000)) * input_rate + (
            Decimal(safe_output_tokens) / Decimal(1_000_000)
        ) * output_rate

        usage.call_count += 1
        usage.input_tokens += safe_input_tokens
        usage.output_tokens += safe_output_tokens
        usage.estimated_cost_usd = float(Decimal(str(usage.estimated_cost_usd)) + estimated_cost)
        usage.updated_at = datetime.now(tz=UTC)
        await self.session.flush()

        await self._maybe_log_alert(today)

    async def get_daily_summary(self) -> dict[str, Any]:
        """Return a compact budget summary for the current UTC date."""
        today = datetime.now(tz=UTC).date()
        query = select(ApiUsage).where(ApiUsage.usage_date == today).order_by(ApiUsage.tier.asc())
        rows = list((await self.session.scalars(query)).all())
        rows_by_tier = {row.tier: row for row in rows}

        tiers: dict[str, dict[str, Any]] = {}
        for tier in KNOWN_TIERS:
            row = rows_by_tier.get(tier)
            tiers[tier] = {
                "calls": int(row.call_count) if row is not None else 0,
                "input_tokens": int(row.input_tokens) if row is not None else 0,
                "output_tokens": int(row.output_tokens) if row is not None else 0,
                "cost_usd": float(row.estimated_cost_usd) if row is not None else 0.0,
                "call_limit": self._call_limit_for_tier(tier),
            }

        total_cost = sum(tier_payload["cost_usd"] for tier_payload in tiers.values())
        daily_limit = float(settings.DAILY_COST_LIMIT_USD)
        budget_remaining = max(0.0, daily_limit - total_cost) if daily_limit > 0 else None

        cost_blocked = daily_limit > 0 and total_cost >= daily_limit
        call_blocked = any(
            tier_payload["call_limit"] > 0 and tier_payload["calls"] >= tier_payload["call_limit"]
            for tier_payload in tiers.values()
        )

        return {
            "date": today.isoformat(),
            "status": "sleep_mode" if (cost_blocked or call_blocked) else "active",
            "daily_cost_limit_usd": daily_limit,
            "total_cost_usd": round(total_cost, 8),
            "budget_remaining_usd": round(budget_remaining, 8)
            if budget_remaining is not None
            else None,
            "tiers": tiers,
        }

    async def _get_or_create_usage(self, usage_date: date, tier: str) -> ApiUsage:
        query = (
            select(ApiUsage)
            .where(ApiUsage.usage_date == usage_date)
            .where(ApiUsage.tier == tier)
            .limit(1)
        )
        usage = await self.session.scalar(query)
        if usage is not None:
            return usage

        usage = ApiUsage(
            usage_date=usage_date,
            tier=tier,
            call_count=0,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
        )
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def _total_cost_for_date(self, usage_date: date) -> Decimal:
        query = (
            select(func.coalesce(func.sum(ApiUsage.estimated_cost_usd), 0))
            .where(ApiUsage.usage_date == usage_date)
            .limit(1)
        )
        total_cost = await self.session.scalar(query)
        return Decimal(str(total_cost))

    async def _maybe_log_alert(self, usage_date: date) -> None:
        daily_limit = float(settings.DAILY_COST_LIMIT_USD)
        threshold_pct = int(settings.COST_ALERT_THRESHOLD_PCT)
        if daily_limit <= 0 or threshold_pct <= 0:
            return

        total_cost = float(await self._total_cost_for_date(usage_date))
        usage_pct = (total_cost / daily_limit) * 100
        if usage_pct < threshold_pct:
            return

        logger.warning(
            "Daily LLM cost alert threshold reached",
            date=usage_date.isoformat(),
            total_cost_usd=round(total_cost, 8),
            daily_limit_usd=daily_limit,
            threshold_pct=threshold_pct,
            usage_pct=round(usage_pct, 2),
        )

    @staticmethod
    def _call_limit_for_tier(tier: str) -> int:
        limits = {
            TIER1: settings.TIER1_MAX_DAILY_CALLS,
            TIER2: settings.TIER2_MAX_DAILY_CALLS,
            EMBEDDING: settings.EMBEDDING_MAX_DAILY_CALLS,
        }
        return int(limits.get(tier, 0))

    @staticmethod
    def _normalize_tier(tier: str) -> str:
        normalized = tier.strip().lower()
        if normalized not in KNOWN_TIERS:
            msg = f"Unsupported cost tracker tier '{tier}'"
            raise ValueError(msg)
        return normalized
