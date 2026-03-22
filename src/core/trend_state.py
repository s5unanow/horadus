"""Helpers for versioned live trend-state activation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.runtime_provenance import current_trend_scoring_contract
from src.storage.trend_state_models import TrendDefinitionVersion, TrendStateVersion

if TYPE_CHECKING:
    from src.storage.models import Trend

TrendActivationKind = Literal["create", "rebase", "replay", "new_line"]


def hash_definition_payload(definition: Any) -> str:
    normalized = definition if isinstance(definition, dict) else {}
    serialized = json.dumps(
        normalized,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def resolve_active_definition_hash(trend: Trend) -> str:
    active_definition_hash = getattr(trend, "active_definition_hash", None)
    if isinstance(active_definition_hash, str) and active_definition_hash:
        return active_definition_hash
    return hash_definition_payload(getattr(trend, "definition", {}))


def resolve_active_scoring_contract(trend: Trend) -> dict[str, str]:
    current = current_trend_scoring_contract()
    active_math_version = getattr(trend, "active_scoring_math_version", None)
    active_parameter_set = getattr(trend, "active_scoring_parameter_set", None)
    return {
        "math_version": (
            active_math_version
            if isinstance(active_math_version, str) and active_math_version
            else current["math_version"]
        ),
        "parameter_set": (
            active_parameter_set
            if isinstance(active_parameter_set, str) and active_parameter_set
            else current["parameter_set"]
        ),
    }


async def ensure_definition_version(
    *,
    session: AsyncSession,
    trend: Trend,
    actor: str | None,
    context: str | None,
) -> TrendDefinitionVersion:
    if trend.active_definition_version_id is not None:
        existing = await session.get(TrendDefinitionVersion, trend.active_definition_version_id)
        if existing is not None:
            return existing

    query = (
        select(TrendDefinitionVersion)
        .where(TrendDefinitionVersion.trend_id == trend.id)
        .order_by(TrendDefinitionVersion.recorded_at.desc())
        .limit(1)
    )
    existing = await session.scalar(query)
    if existing is not None:
        return cast("TrendDefinitionVersion", existing)

    if trend.id is None:
        msg = "Trend id is required before creating a definition version"
        raise ValueError(msg)

    definition_version = TrendDefinitionVersion(
        trend_id=trend.id,
        definition_hash=hash_definition_payload(trend.definition),
        definition=trend.definition if isinstance(trend.definition, dict) else {},
        actor=actor,
        context=context,
    )
    session.add(definition_version)
    await session.flush()
    return definition_version


async def activate_trend_state(
    *,
    session: AsyncSession,
    trend: Trend,
    activation_kind: TrendActivationKind,
    actor: str | None,
    context: str | None,
    definition_version: TrendDefinitionVersion | None = None,
    activated_at: datetime | None = None,
    details: dict[str, Any] | None = None,
) -> TrendStateVersion:
    if trend.id is None:
        msg = "Trend id is required before activating a state version"
        raise ValueError(msg)

    definition_version = definition_version or await ensure_definition_version(
        session=session,
        trend=trend,
        actor=actor,
        context=context,
    )
    contract = current_trend_scoring_contract()
    activated = activated_at.astimezone(UTC) if activated_at is not None else datetime.now(UTC)
    previous_state_id = trend.active_state_version_id
    baseline_log_odds = float(trend.baseline_log_odds)
    current_log_odds = float(trend.current_log_odds)
    if activation_kind in {"replay", "new_line"}:
        starting_log_odds = baseline_log_odds
    else:
        starting_log_odds = current_log_odds

    state_details = dict(details or {})
    if activation_kind == "replay":
        state_details.setdefault("isolation_strategy", "cutoff_freeze")
        state_details.setdefault("replay_required", True)
    if activation_kind == "new_line":
        state_details.setdefault("isolation_strategy", "fresh_line")

    state_version = TrendStateVersion(
        trend_id=trend.id,
        parent_state_version_id=previous_state_id,
        definition_version_id=definition_version.id,
        definition_hash=definition_version.definition_hash,
        activation_kind=activation_kind,
        scoring_math_version=contract["math_version"],
        scoring_parameter_set=contract["parameter_set"],
        baseline_log_odds=baseline_log_odds,
        starting_log_odds=starting_log_odds,
        current_log_odds=starting_log_odds,
        decay_half_life_days=int(trend.decay_half_life_days),
        actor=actor,
        context=context,
        details=state_details or None,
        activated_at=activated,
    )
    session.add(state_version)
    await session.flush()

    trend.active_definition_version_id = definition_version.id
    trend.active_definition_hash = definition_version.definition_hash
    trend.active_scoring_math_version = contract["math_version"]
    trend.active_scoring_parameter_set = contract["parameter_set"]
    trend.active_state_version_id = state_version.id
    trend.current_log_odds = starting_log_odds
    trend.updated_at = activated
    return state_version
