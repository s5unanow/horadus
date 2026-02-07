from __future__ import annotations

import pytest

from src.api.routes.budget import get_budget_status
from src.processing.cost_tracker import CostTracker

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_budget_status_returns_tracker_summary(mock_db_session, monkeypatch) -> None:
    async def fake_summary(_self):
        return {
            "date": "2026-02-07",
            "status": "active",
            "daily_cost_limit_usd": 5.0,
            "total_cost_usd": 1.2,
            "budget_remaining_usd": 3.8,
            "tiers": {
                "tier1": {
                    "calls": 10,
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cost_usd": 0.2,
                    "call_limit": 1000,
                },
                "tier2": {
                    "calls": 2,
                    "input_tokens": 800,
                    "output_tokens": 300,
                    "cost_usd": 1.0,
                    "call_limit": 200,
                },
                "embedding": {
                    "calls": 5,
                    "input_tokens": 5000,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "call_limit": 500,
                },
            },
        }

    monkeypatch.setattr(CostTracker, "get_daily_summary", fake_summary)

    result = await get_budget_status(session=mock_db_session)

    assert result.status == "active"
    assert result.total_cost_usd == pytest.approx(1.2)
    assert result.tiers["tier1"]["calls"] == 10
