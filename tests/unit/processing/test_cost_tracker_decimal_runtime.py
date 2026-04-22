from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.core.config import settings
from src.processing.cost_tracker import CostTracker
from src.storage.models import ApiUsage

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_record_usage_keeps_estimated_cost_as_decimal(mock_db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_USD", 10.0)
    monkeypatch.setattr(settings, "COST_ALERT_THRESHOLD_PCT", 80)
    today = datetime.now(tz=UTC).date()
    usage = ApiUsage(
        usage_date=today,
        tier="tier1",
        call_count=0,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0,
    )
    mock_db_session.scalar.side_effect = [usage, Decimal("0.3")]
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [usage])

    await CostTracker(session=mock_db_session).record_usage(
        tier="tier1",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )

    assert isinstance(usage.estimated_cost_usd, Decimal)
