from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

import src.api.routes._trend_write_mutations as trend_write_mutations_module
import src.api.routes.trends as trends_module
from src.storage.models import TrendDefinitionVersion, TrendStateVersion


@pytest.fixture(autouse=True)
def patch_state_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_ensure_definition_version(*, session, trend, actor, context):
        for call in reversed(session.add.call_args_list):
            candidate = call.args[0]
            if isinstance(candidate, TrendDefinitionVersion) and candidate.trend_id == trend.id:
                return candidate
        definition_version = TrendDefinitionVersion(
            id=uuid4(),
            trend_id=trend.id or uuid4(),
            definition_hash="d" * 64,
            definition=trend.definition if isinstance(trend.definition, dict) else {},
            actor=actor,
            context=context,
            recorded_at=datetime.now(tz=UTC),
        )
        session.add(definition_version)
        return definition_version

    async def _fake_activate_trend_state(
        *,
        session,
        trend,
        activation_kind,
        actor,
        context,
        definition_version,
        details=None,
        activated_at=None,
    ):
        activated = activated_at or datetime.now(tz=UTC)
        state_version = TrendStateVersion(
            id=uuid4(),
            trend_id=trend.id or uuid4(),
            definition_version_id=definition_version.id,
            definition_hash=definition_version.definition_hash,
            activation_kind=activation_kind,
            scoring_math_version="trend-scoring-v1",
            scoring_parameter_set="stable-default-v1",
            baseline_log_odds=float(trend.baseline_log_odds),
            starting_log_odds=(
                float(trend.baseline_log_odds)
                if activation_kind in {"replay", "new_line"}
                else float(trend.current_log_odds)
            ),
            current_log_odds=(
                float(trend.baseline_log_odds)
                if activation_kind in {"replay", "new_line"}
                else float(trend.current_log_odds)
            ),
            decay_half_life_days=trend.decay_half_life_days,
            actor=actor,
            context=context,
            details=details,
            activated_at=activated,
        )
        session.add(state_version)
        trend.active_definition_version_id = definition_version.id
        trend.active_definition_hash = definition_version.definition_hash
        trend.active_scoring_math_version = "trend-scoring-v1"
        trend.active_scoring_parameter_set = "stable-default-v1"
        trend.active_state_version_id = state_version.id
        if activation_kind in {"replay", "new_line"}:
            trend.current_log_odds = trend.baseline_log_odds
        trend.updated_at = activated
        return state_version

    monkeypatch.setattr(trends_module, "ensure_definition_version", _fake_ensure_definition_version)
    monkeypatch.setattr(trends_module, "activate_trend_state", _fake_activate_trend_state)
    monkeypatch.setattr(
        trend_write_mutations_module,
        "ensure_definition_version",
        _fake_ensure_definition_version,
    )
    monkeypatch.setattr(
        trend_write_mutations_module,
        "activate_trend_state",
        _fake_activate_trend_state,
    )
