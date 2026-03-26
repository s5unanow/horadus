from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.core.report_statistics as report_statistics_module
from src.core.trend_state_presentation import (
    EvidenceWindowStats,
    TrendMomentumState,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_build_report_uncertainty_state_raises_when_trend_id_missing(
    mock_db_session,
) -> None:
    with pytest.raises(ValueError, match="Trend id is required"):
        await report_statistics_module.build_report_uncertainty_state(
            mock_db_session,
            trend=SimpleNamespace(id=None),
            probability=0.4,
        )


@pytest.mark.asyncio
async def test_build_report_uncertainty_state_returns_serialized_payload(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = AsyncMock(
        return_value=EvidenceWindowStats(
            evidence_count=8,
            avg_corroboration=0.75,
            days_since_last_evidence=1,
        )
    )
    monkeypatch.setattr(report_statistics_module, "load_evidence_window_stats", loader)
    trend = SimpleNamespace(id=uuid4(), active_state_version_id=uuid4())

    result = await report_statistics_module.build_report_uncertainty_state(
        mock_db_session,
        trend=trend,
        probability=0.2,
    )

    assert result["level"] == "medium"
    assert loader.await_args.kwargs["state_version_id"] == trend.active_state_version_id


@pytest.mark.asyncio
async def test_build_report_momentum_state_returns_serialized_payload(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = AsyncMock(
        return_value=TrendMomentumState(
            direction="rising",
            window_days=7,
            delta_probability=0.03,
            previous_window_delta=0.01,
            acceleration=0.02,
            evidence_count_window=4,
        )
    )
    monkeypatch.setattr(report_statistics_module, "build_momentum_state", builder)
    trend = SimpleNamespace(id=uuid4(), active_state_version_id=uuid4())
    trend_engine = SimpleNamespace()

    result = await report_statistics_module.build_report_momentum_state(
        mock_db_session,
        trend=trend,
        trend_engine=trend_engine,
    )

    assert result["direction"] == "rising"
    assert builder.await_args.kwargs["state_version_id"] == trend.active_state_version_id
