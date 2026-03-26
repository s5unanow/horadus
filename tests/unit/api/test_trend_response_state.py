from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.api.routes.trends as trends_module
from src.api.routes.trends import list_trends
from src.core.trend_engine import prob_to_logodds
from src.storage.models import Trend
from tests.unit.trend_forecast_contract_fixtures import sample_binary_forecast_contract

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_list_trends_exposes_uncertainty_and_momentum(mock_db_session, monkeypatch) -> None:
    async def _fake_evidence_stats(*_args: object, **_kwargs: object) -> tuple[int, float, int]:
        return 8, 0.75, 1

    async def _fake_momentum_state(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "direction": "rising",
            "window_days": 7,
            "delta_probability": 0.03,
            "previous_window_delta": 0.01,
            "acceleration": 0.02,
            "evidence_count_window": 4,
        }

    async def _fake_top_movers(*_args: object, **_kwargs: object) -> list[str]:
        return ["Signal corroborated across multiple outlets"]

    monkeypatch.setattr(trends_module, "_get_evidence_stats", _fake_evidence_stats)
    monkeypatch.setattr(trends_module, "_get_momentum_state", _fake_momentum_state)
    monkeypatch.setattr(trends_module, "_get_top_movers_7d", _fake_top_movers)

    now = datetime.now(tz=UTC)
    trend = Trend(
        id=uuid4(),
        name="Test Trend",
        description="Trend description",
        runtime_trend_id="test-trend",
        definition={"id": "test-trend", "forecast_contract": sample_binary_forecast_contract()},
        baseline_log_odds=prob_to_logodds(0.1),
        current_log_odds=prob_to_logodds(0.2),
        indicators={"signal": {"direction": "escalatory", "weight": 0.04, "keywords": ["x"]}},
        decay_half_life_days=30,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [trend])

    result = await list_trends(session=mock_db_session, sync_from_config=False)

    assert result[0].uncertainty.level == "medium"
    assert result[0].uncertainty.score == pytest.approx(0.3255, rel=0.01)
    assert result[0].momentum.direction == "rising"
    assert result[0].momentum.acceleration == pytest.approx(0.02)
