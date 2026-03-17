"""
Trend configuration schema validation for YAML files.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

import src.core.trend_forecast_contract as trend_forecast_contract_module  # noqa: TC001

MAX_RUNTIME_TREND_ID_LENGTH = 255
DEFAULT_TREND_CONFIG_SYNC_DIR = "config/trends"
REPO_TREND_CONFIG_ROOT = (Path(__file__).resolve().parents[2] / "config" / "trends").resolve()


class TrendConfigSyncPathError(ValueError):
    """Raised when a sync request points outside the repo-owned trend-config root."""


class TrendDisqualifier(BaseModel):
    """Condition that invalidates or resets a trend estimate."""

    signal: str = Field(..., min_length=1)
    effect: Literal["reset_to_baseline", "reassess", "invalidate"]
    description: str = Field(..., min_length=1)


class TrendFalsificationCriteria(BaseModel):
    """Human-readable criteria that would change confidence in the model."""

    decrease_confidence: list[str] = Field(default_factory=list)
    increase_confidence: list[str] = Field(default_factory=list)
    would_invalidate_model: list[str] = Field(default_factory=list)


class TrendIndicatorConfig(BaseModel):
    """Indicator configuration for one signal type."""

    weight: float = Field(..., ge=0.0, le=1.0)
    direction: Literal["escalatory", "de_escalatory"]
    type: Literal["leading", "lagging"] = "leading"
    decay_half_life_days: int | None = Field(default=None, ge=1)
    description: str | None = Field(default=None, min_length=1)
    keywords: list[str] = Field(default_factory=list)


class TrendConfig(BaseModel):
    """Validated shape for `config/trends/*.yaml` files."""

    model_config = ConfigDict(extra="allow")

    id: str | None = Field(default=None, max_length=MAX_RUNTIME_TREND_ID_LENGTH)
    name: str = Field(..., min_length=1)
    description: str | None = None
    baseline_probability: float = Field(..., ge=0.0, le=1.0)
    decay_half_life_days: int = Field(default=30, ge=1)
    forecast_contract: trend_forecast_contract_module.TrendForecastContract | None = None
    indicators: dict[str, TrendIndicatorConfig] = Field(default_factory=dict)
    disqualifiers: list[TrendDisqualifier] = Field(default_factory=list)
    falsification_criteria: TrendFalsificationCriteria = Field(
        default_factory=TrendFalsificationCriteria
    )


def slugify_trend_name(name: str) -> str:
    """Normalize a trend name into the default runtime identifier shape."""

    normalized = "-".join(name.lower().strip().split())
    return normalized.replace("/", "-").replace("_", "-")


def _validate_runtime_trend_id_length(runtime_trend_id: str) -> str:
    if len(runtime_trend_id) <= MAX_RUNTIME_TREND_ID_LENGTH:
        return runtime_trend_id

    msg = f"Trend runtime id cannot exceed {MAX_RUNTIME_TREND_ID_LENGTH} characters"
    raise ValueError(msg)


def normalize_definition_payload(definition: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a mutable definition mapping for downstream normalization."""

    return dict(definition) if isinstance(definition, Mapping) else {}


def resolve_trend_config_sync_dir(
    config_dir: str | Path = DEFAULT_TREND_CONFIG_SYNC_DIR,
) -> Path:
    """Resolve a sync request path within the repo-owned `config/trends` root."""

    raw_value = str(config_dir).strip()
    if not raw_value or raw_value == ".":
        relative_path = Path()
    else:
        requested_path = Path(raw_value)
        if requested_path.is_absolute():
            msg = "config_dir must be relative to the repo-owned config/trends root"
            raise TrendConfigSyncPathError(msg)

        if ".." in requested_path.parts:
            msg = "config_dir cannot contain path traversal segments"
            raise TrendConfigSyncPathError(msg)

        if requested_path.parts[:2] == ("config", "trends"):
            relative_path = Path(*requested_path.parts[2:])
        else:
            relative_path = requested_path

    resolved_path = (REPO_TREND_CONFIG_ROOT / relative_path).resolve()
    if not resolved_path.is_relative_to(REPO_TREND_CONFIG_ROOT):
        msg = "config_dir must resolve within the repo-owned config/trends root"
        raise TrendConfigSyncPathError(msg)

    return resolved_path


def resolve_runtime_trend_id(*, definition: Mapping[str, Any] | None, trend_name: str) -> str:
    """Resolve the runtime taxonomy identifier used by Tier-1/Tier-2/pipeline routing."""

    normalized_definition = normalize_definition_payload(definition)
    raw_id = normalized_definition.get("id")
    if isinstance(raw_id, str):
        normalized_id = raw_id.strip()
        if normalized_id:
            return _validate_runtime_trend_id_length(normalized_id)

    fallback_id = slugify_trend_name(trend_name)
    if fallback_id:
        return _validate_runtime_trend_id_length(fallback_id)

    msg = "Trend runtime id cannot be blank"
    raise ValueError(msg)


def validate_trend_config_payload(
    payload: Mapping[str, Any], *, require_forecast_contract: bool = True
) -> TrendConfig:
    """Validate a trend payload and enforce forecast-contract requirements when requested."""

    validated_config = TrendConfig.model_validate(dict(payload))
    if require_forecast_contract and validated_config.forecast_contract is None:
        msg = "forecast_contract is required"
        raise ValueError(msg)
    return validated_config


def build_trend_config(
    *,
    name: str,
    description: str | None,
    baseline_probability: float,
    decay_half_life_days: int,
    indicators: Mapping[str, Any] | None,
    definition: Mapping[str, Any] | None = None,
    require_forecast_contract: bool = True,
) -> TrendConfig:
    """Validate a full trend payload against the canonical taxonomy contract."""

    normalized_definition = normalize_definition_payload(definition)
    payload = dict(normalized_definition)
    payload.update(
        {
            "id": resolve_runtime_trend_id(definition=normalized_definition, trend_name=name),
            "name": name,
            "description": description,
            "baseline_probability": baseline_probability,
            "decay_half_life_days": decay_half_life_days,
            "indicators": dict(indicators) if isinstance(indicators, Mapping) else indicators,
        }
    )
    return validate_trend_config_payload(
        payload,
        require_forecast_contract=require_forecast_contract,
    )


def trend_runtime_id_for_record(trend: Any) -> str:
    """Resolve the canonical runtime trend id from a trend-like object."""

    runtime_trend_id = getattr(trend, "runtime_trend_id", None)
    if isinstance(runtime_trend_id, str) and runtime_trend_id.strip():
        return runtime_trend_id.strip()

    definition = getattr(trend, "definition", None)
    normalized_definition = normalize_definition_payload(
        definition if isinstance(definition, Mapping) else None
    )
    definition_id = normalized_definition.get("id")
    if isinstance(definition_id, str) and definition_id.strip():
        return definition_id.strip()

    msg = f"Trend '{getattr(trend, 'name', '')}' is missing runtime_trend_id"
    raise ValueError(msg)


def index_trends_by_runtime_id(trends: Sequence[Any]) -> dict[str, Any]:
    """Build a runtime-id keyed map and fail closed on duplicates."""

    trend_by_id: dict[str, Any] = {}
    for trend in trends:
        runtime_trend_id = trend_runtime_id_for_record(trend)
        if runtime_trend_id in trend_by_id:
            msg = f"Duplicate active runtime_trend_id '{runtime_trend_id}'"
            raise ValueError(msg)
        trend_by_id[runtime_trend_id] = trend
    return trend_by_id
