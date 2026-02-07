"""
Budget visibility endpoint for LLM cost protection.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.processing.cost_tracker import CostTracker
from src.storage.database import get_session

router = APIRouter()


class BudgetSummary(BaseModel):
    """Current UTC day budget status."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2026-02-07",
                "status": "active",
                "daily_cost_limit_usd": 5.0,
                "total_cost_usd": 1.42,
                "budget_remaining_usd": 3.58,
                "tiers": {
                    "tier1": {
                        "calls": 142,
                        "input_tokens": 32000,
                        "output_tokens": 8000,
                        "cost_usd": 0.18,
                        "call_limit": 1000,
                    },
                    "tier2": {
                        "calls": 28,
                        "input_tokens": 45000,
                        "output_tokens": 12000,
                        "cost_usd": 1.24,
                        "call_limit": 200,
                    },
                    "embedding": {
                        "calls": 89,
                        "input_tokens": 91000,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "call_limit": 500,
                    },
                },
            }
        }
    )

    date: str
    status: str
    daily_cost_limit_usd: float
    total_cost_usd: float
    budget_remaining_usd: float | None
    tiers: dict[str, dict[str, Any]]


@router.get("", response_model=BudgetSummary)
async def get_budget_status(
    session: AsyncSession = Depends(get_session),
) -> BudgetSummary:
    """
    Return daily LLM usage and remaining budget.

    Includes per-tier calls/tokens/cost, overall cost limit, and status.
    """
    tracker = CostTracker(session=session)
    summary = await tracker.get_daily_summary()
    return BudgetSummary.model_validate(summary)
