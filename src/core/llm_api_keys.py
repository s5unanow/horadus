"""Helpers for resolving tier-specific LLM API keys."""

from __future__ import annotations

from typing import Literal

from src.core.config import settings

LLMTier = Literal["tier1", "tier2"]

_TIER_API_KEY_FIELDS: dict[LLMTier, str] = {
    "tier1": "LLM_TIER1_API_KEY",
    "tier2": "LLM_TIER2_API_KEY",
}


def _trimmed(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_tier_api_key(
    tier: LLMTier,
    *,
    settings_obj: object = settings,
    fallback_api_key: str | None = None,
) -> str:
    """Return the primary API key for an LLM tier."""
    tier_key = _trimmed(getattr(settings_obj, _TIER_API_KEY_FIELDS[tier], ""))
    if tier_key:
        return tier_key

    fallback_key = _trimmed(fallback_api_key)
    if fallback_key:
        return fallback_key

    return _trimmed(getattr(settings_obj, "OPENAI_API_KEY", ""))


def resolve_secondary_api_key(
    tier: LLMTier,
    *,
    settings_obj: object = settings,
    fallback_api_key: str | None = None,
) -> str:
    """Return the secondary API key for a tier failover route."""
    secondary_key = _trimmed(getattr(settings_obj, "LLM_SECONDARY_API_KEY", ""))
    if secondary_key:
        return secondary_key

    return resolve_tier_api_key(
        tier,
        settings_obj=settings_obj,
        fallback_api_key=fallback_api_key,
    )
