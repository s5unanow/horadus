"""Scope controls shared by offline benchmark entry points."""

from __future__ import annotations

from typing import Any

BENCHMARK_TIER_SCOPE_FULL = "full"
BENCHMARK_TIER_SCOPE_TIER2 = "tier2"
BENCHMARK_TIER_SCOPES = (BENCHMARK_TIER_SCOPE_FULL, BENCHMARK_TIER_SCOPE_TIER2)
DISPATCH_MODE_REALTIME = "realtime"
DISPATCH_MODE_BATCH = "batch"
REQUEST_PRIORITY_REALTIME = "realtime"
REQUEST_PRIORITY_FLEX = "flex"
BATCH_DISPATCH_SIZE = 10
SAFE_TIER1_BATCH_SIZE = 1
TIER1_BATCH_POLICY_SAFE_DEFAULT = "safe_single_item_default"
TIER1_BATCH_POLICY_DIAGNOSTIC = "diagnostic_multi_item_batch"
TIER1_BATCH_POLICY_SKIPPED_TIER2 = "skipped_tier2_scope"


def _normalize_tier_scope(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in BENCHMARK_TIER_SCOPES:
        msg = f"Unsupported tier scope '{value}'. Allowed: {', '.join(BENCHMARK_TIER_SCOPES)}"
        raise ValueError(msg)
    return normalized


def _normalize_dispatch_mode(value: str) -> str:
    normalized = value.strip().lower()
    allowed = {DISPATCH_MODE_REALTIME, DISPATCH_MODE_BATCH}
    if normalized not in allowed:
        msg = f"Unsupported dispatch mode '{value}'. Allowed: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return normalized


def _normalize_request_priority(value: str) -> str:
    normalized = value.strip().lower()
    allowed = {REQUEST_PRIORITY_REALTIME, REQUEST_PRIORITY_FLEX}
    if normalized not in allowed:
        msg = f"Unsupported request priority '{value}'. Allowed: {', '.join(sorted(allowed))}"
        raise ValueError(msg)
    return normalized


def _request_overrides_for_priority(priority: str) -> dict[str, Any] | None:
    if priority == REQUEST_PRIORITY_FLEX:
        return {"service_tier": "flex"}
    return None


def _merge_request_overrides(*overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for override in overrides:
        if isinstance(override, dict):
            merged.update(override)
    return merged or None


def _tier1_batch_settings_for_dispatch(dispatch_mode: str) -> tuple[int, str]:
    if dispatch_mode == DISPATCH_MODE_REALTIME:
        return (SAFE_TIER1_BATCH_SIZE, TIER1_BATCH_POLICY_SAFE_DEFAULT)
    return (BATCH_DISPATCH_SIZE, TIER1_BATCH_POLICY_DIAGNOSTIC)


def _select_items_for_tier_scope[T](
    items: list[T],
    *,
    tier_scope: str,
    max_items: int,
) -> list[T]:
    bounded_max_items = max(1, max_items)
    if tier_scope == BENCHMARK_TIER_SCOPE_FULL:
        return items[:bounded_max_items]
    selected = [item for item in items if getattr(item, "tier2", None) is not None]
    return selected[:bounded_max_items]
