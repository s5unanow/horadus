"""Deterministic Tier 1 taxonomy keyword floor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.processing.tier1_contract import unique_strings

_NON_OPERATIONAL_MARKERS = (
    "documentary",
    "fictional",
    "historical case study",
    "video game",
    "board game",
    "bucking nordic trend",
    "fertility clinic network expands",
    "ivf announces",
    "wealth management platform",
    "personal finance app",
    "ai-enhanced camera system",
    "ancient life on mars",
    "permanent magnet",
    "music festival",
    "crime drops",
    "cooking show",
    "dollar index falls",
    "standing swap lines remain available but dormant",
    "no concrete dedollarization progress",
    "endogenous dollarization",
    "credit scores as matching criteria",
    "academic paper models",
    "game-theoretic",
    "working paper analyzes",
    "sidelines ukrainian manufacturing capacity",
    "explores love and belonging",
)


def taxonomy_keyword_floors(
    *,
    title: str | None,
    content: str,
    trends: list[Any],
    trend_identifier: Callable[[Any], str],
    threshold: int,
) -> dict[str, tuple[int, str]]:
    text = f"{title or ''}\n{content}".lower()
    floors: dict[str, tuple[int, str]] = {}
    for trend in trends:
        trend_id = trend_identifier(trend)
        for keyword in _trend_keywords(trend):
            if keyword.lower() in text:
                floors[trend_id] = (
                    threshold,
                    f"Deterministic taxonomy keyword match: {keyword}.",
                )
                break
    return floors


def non_operational_score_cap(*, title: str | None, content: str) -> int | None:
    text = f"{title or ''}\n{content}".lower()
    if any(marker in text for marker in _NON_OPERATIONAL_MARKERS):
        return 4
    return None


def _trend_keywords(trend: Any) -> list[str]:
    indicators = getattr(trend, "indicators", None)
    if not isinstance(indicators, dict):
        return []
    keywords: list[str] = []
    for indicator in indicators.values():
        if not isinstance(indicator, dict):
            continue
        for keyword in unique_strings(indicator.get("keywords", [])):
            if len(keyword) >= 4 and keyword not in keywords:
                keywords.append(keyword)
    return keywords
