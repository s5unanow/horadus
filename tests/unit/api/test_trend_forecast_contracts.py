from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

import src.api.routes.trends as trends_module
import src.core.trend_config as trend_config_module
from src.api.routes.trends import (
    TrendCreate,
    TrendUpdate,
    create_trend,
    load_trends_from_config,
    update_trend,
)
from src.core.trend_engine import prob_to_logodds
from src.storage.models import Trend
from tests.unit.trend_forecast_contract_fixtures import sample_binary_forecast_contract

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_risk_presentation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_evidence_stats(*_args: object, **_kwargs: object) -> tuple[int, float, int]:
        return 0, 0.5, 30

    async def _fake_top_movers(*_args: object, **_kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(trends_module, "_get_evidence_stats", _fake_evidence_stats)
    monkeypatch.setattr(trends_module, "_get_top_movers_7d", _fake_top_movers)


def _build_trend() -> Trend:
    now = datetime.now(tz=UTC)
    return Trend(
        id=uuid4(),
        name="Contract Trend",
        description="Trend description",
        runtime_trend_id="contract-trend",
        definition={
            "id": "contract-trend",
            "forecast_contract": sample_binary_forecast_contract(),
        },
        baseline_log_odds=prob_to_logodds(0.1),
        current_log_odds=prob_to_logodds(0.2),
        indicators={"signal": {"direction": "escalatory", "weight": 0.04, "keywords": ["x"]}},
        decay_half_life_days=30,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _build_legacy_trend_without_contract() -> Trend:
    trend = _build_trend()
    trend.definition = {"id": "contract-trend"}
    return trend


@pytest.mark.asyncio
async def test_create_trend_round_trips_forecast_contract(mock_db_session) -> None:
    created_id = uuid4()
    mock_db_session.scalar.return_value = None

    async def flush_side_effect() -> None:
        trend_record = mock_db_session.add.call_args.args[0]
        trend_record.id = created_id
        trend_record.updated_at = datetime.now(tz=UTC)

    mock_db_session.flush.side_effect = flush_side_effect

    result = await create_trend(
        trend=TrendCreate(
            name="Contract Trend",
            baseline_probability=0.08,
            forecast_contract=sample_binary_forecast_contract(),
            indicators={"signal": {"direction": "escalatory", "weight": 0.04}},
        ),
        session=mock_db_session,
    )

    added_trend = next(
        obj
        for obj in (call.args[0] for call in mock_db_session.add.call_args_list)
        if isinstance(obj, Trend)
    )
    assert result.forecast_contract is not None
    assert result.forecast_contract.question == "Will a test conflict occur by 2030-12-31?"
    assert added_trend.definition["forecast_contract"]["closure_rule"] == "binary_event_by_horizon"


@pytest.mark.asyncio
async def test_create_trend_rejects_missing_forecast_contract(mock_db_session) -> None:
    with pytest.raises(ValidationError, match="forecast_contract"):
        TrendCreate(
            name="Missing Contract",
            baseline_probability=0.08,
            indicators={"signal": {"direction": "escalatory", "weight": 0.04}},
        )


@pytest.mark.asyncio
async def test_load_trends_from_config_reports_missing_horizon(
    mock_db_session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trend_config_module, "REPO_TREND_CONFIG_ROOT", tmp_path.resolve())
    config_file = tmp_path / "missing-horizon.yaml"
    config_file.write_text(
        """
id: missing-horizon
name: Missing Horizon
baseline_probability: 0.12
decay_half_life_days: 20
forecast_contract:
  question: "Will a test conflict occur by 2030-12-31?"
  horizon:
    kind: fixed_date
  resolution_basis: "Binary event question resolved against confirmed direct conflict."
  resolver_source: "Official statements plus multi-source corroborated reporting."
  resolver_basis: "Resolve yes on confirmed conflict; otherwise resolve no at horizon."
  closure_rule: "binary_event_by_horizon"
  occurrence_definition: "Confirmed direct conflict occurs."
  non_occurrence_definition: "No confirmed direct conflict occurs by the horizon date."
indicators:
  signal:
    weight: 0.04
    direction: escalatory
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = await load_trends_from_config(mock_db_session, config_dir=".")

    assert result.created == 0
    assert result.updated == 0
    assert len(result.errors) == 1
    assert "missing-horizon.yaml" in result.errors[0]
    assert "horizon" in result.errors[0]


@pytest.mark.asyncio
async def test_load_trends_from_config_supports_enhanced_fields(
    mock_db_session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trend_config_module, "REPO_TREND_CONFIG_ROOT", tmp_path.resolve())
    config_file = tmp_path / "enhanced-trend.yaml"
    config_file.write_text(
        """
id: enhanced-trend
name: Enhanced Trend
baseline_probability: 0.20
decay_half_life_days: 15
forecast_contract:
  question: "Will a test conflict occur by 2030-12-31?"
  horizon:
    kind: fixed_date
    fixed_date: 2030-12-31
  resolution_basis: "Binary event question resolved against confirmed direct conflict."
  resolver_source: "Official statements plus multi-source corroborated reporting."
  resolver_basis: "Resolve yes on confirmed conflict; otherwise resolve no at horizon."
  closure_rule: "binary_event_by_horizon"
  occurrence_definition: "Confirmed direct conflict occurs."
  non_occurrence_definition: "No confirmed direct conflict occurs by the horizon date."
disqualifiers:
  - signal: peace_treaty
    effect: reset_to_baseline
    description: Signed peace treaty
falsification_criteria:
  decrease_confidence:
    - Sustained de-escalation
indicators:
  military_movement:
    weight: 0.04
    direction: escalatory
    type: leading
    decay_half_life_days: 10
    keywords: ["troops"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    mock_db_session.scalar.side_effect = [None, None]

    result = await load_trends_from_config(mock_db_session, config_dir=".")

    assert result.created == 1
    assert result.errors == []
    added_trend = next(
        obj
        for obj in (call.args[0] for call in mock_db_session.add.call_args_list)
        if isinstance(obj, Trend)
    )
    assert added_trend.indicators["military_movement"]["type"] == "leading"
    assert added_trend.indicators["military_movement"]["decay_half_life_days"] == 10
    assert added_trend.definition["disqualifiers"][0]["effect"] == "reset_to_baseline"
    assert added_trend.definition["falsification_criteria"]["decrease_confidence"] == [
        "Sustained de-escalation"
    ]


@pytest.mark.asyncio
async def test_update_trend_accepts_forecast_contract_only_patch(mock_db_session) -> None:
    trend = _build_trend()
    mock_db_session.get.return_value = trend
    mock_db_session.scalar.return_value = None

    result = await update_trend(
        trend_id=trend.id,
        trend=TrendUpdate(
            forecast_contract=sample_binary_forecast_contract(
                question="Will an updated test conflict occur by 2030-12-31?"
            )
        ),
        session=mock_db_session,
    )

    assert result.forecast_contract is not None
    assert result.forecast_contract.question == "Will an updated test conflict occur by 2030-12-31?"
    assert (
        trend.definition["forecast_contract"]["question"]
        == "Will an updated test conflict occur by 2030-12-31?"
    )


@pytest.mark.asyncio
async def test_update_trend_allows_unrelated_patch_for_legacy_rows_without_contract(
    mock_db_session,
) -> None:
    trend = _build_legacy_trend_without_contract()
    mock_db_session.get.return_value = trend
    mock_db_session.scalar.return_value = None

    result = await update_trend(
        trend_id=trend.id,
        trend=TrendUpdate(is_active=False),
        session=mock_db_session,
    )

    assert trend.is_active is False
    assert result.is_active is False
