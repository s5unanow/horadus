"""Persistence and state-version helpers for the standalone trend seeder."""

from __future__ import annotations

from math import isclose
from typing import Any
from uuid import uuid4

from src.core.trend_engine import DEFAULT_DECAY_HALF_LIFE_DAYS, prob_to_logodds
from src.core.trend_state import activate_trend_state, hash_definition_payload
from src.storage.models import Trend, to_decimal
from src.storage.trend_state_models import TrendDefinitionVersion

DEFAULT_BASELINE_PROBABILITY = 0.10


def _seed_values(definition: dict[str, Any]) -> tuple[float, int, dict[str, Any]]:
    baseline_log_odds = prob_to_logodds(
        float(definition.get("baseline_probability", DEFAULT_BASELINE_PROBABILITY))
    )
    decay_half_life_days = int(definition.get("decay_half_life_days", DEFAULT_DECAY_HALF_LIFE_DAYS))
    indicators = definition.get("indicators") or {}
    return baseline_log_odds, decay_half_life_days, indicators


async def ensure_seeded_trend_state(
    session: Any,
    trend: Trend,
    source_file: str,
    *,
    rebase: bool = False,
    definition_version: TrendDefinitionVersion | None = None,
) -> None:
    """Create a missing initial state or rebase a materially changed seed."""
    active_state_version_id = trend.active_state_version_id
    if active_state_version_id is not None and not rebase:
        return
    await session.flush()
    await activate_trend_state(
        session=session,
        trend=trend,
        activation_kind="rebase" if active_state_version_id is not None else "create",
        actor="system",
        context=f"seed_trends:{source_file}",
        details={"source_file": source_file},
        definition_version=definition_version,
    )


async def _create_seed_definition_version(
    session: Any,
    trend: Trend,
    source_file: str,
) -> TrendDefinitionVersion:
    if trend.id is None:
        msg = "Trend id is required before creating a seed definition version"
        raise ValueError(msg)
    definition = trend.definition if isinstance(trend.definition, dict) else {}
    definition_version = TrendDefinitionVersion(
        id=uuid4(),
        trend_id=trend.id,
        definition_hash=hash_definition_payload(definition),
        definition=definition,
        actor="system",
        context=f"seed_trends:{source_file}",
    )
    session.add(definition_version)
    await session.flush()
    return definition_version


async def create_seeded_trend(
    session: Any,
    definition: dict[str, Any],
    source_file: str,
) -> Trend:
    """Persist a new seeded trend and activate its initial state."""
    baseline_log_odds, decay_half_life_days, indicators = _seed_values(definition)
    trend = Trend(
        name=str(definition["name"]).strip(),
        description=definition.get("description"),
        runtime_trend_id=str(definition["id"]),
        definition=definition,
        baseline_log_odds=baseline_log_odds,
        current_log_odds=baseline_log_odds,
        indicators=indicators,
        decay_half_life_days=decay_half_life_days,
        is_active=True,
    )
    session.add(trend)
    await ensure_seeded_trend_state(session, trend, source_file)
    return trend


async def sync_seeded_trend(
    session: Any,
    trend: Trend,
    definition: dict[str, Any],
    source_file: str,
) -> None:
    """Update a seeded trend and rebase lineage only for material changes."""
    baseline_log_odds, decay_half_life_days, indicators = _seed_values(definition)
    definition_changed = trend.definition != definition
    state_changed = (
        definition_changed
        or not isclose(float(trend.baseline_log_odds), baseline_log_odds, abs_tol=1e-6)
        or trend.indicators != indicators
        or trend.decay_half_life_days != decay_half_life_days
    )
    trend.name, trend.description = str(definition["name"]).strip(), definition.get("description")
    trend.runtime_trend_id, trend.definition = str(definition["id"]), definition
    trend.indicators, trend.decay_half_life_days = indicators, decay_half_life_days
    trend.baseline_log_odds = to_decimal(baseline_log_odds)
    definition_version = (
        await _create_seed_definition_version(session, trend, source_file)
        if state_changed and definition_changed
        else None
    )
    await ensure_seeded_trend_state(
        session,
        trend,
        source_file,
        rebase=state_changed,
        definition_version=definition_version,
    )
