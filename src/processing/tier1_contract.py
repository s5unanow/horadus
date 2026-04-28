"""Tier 1 payload and output-contract helpers."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from typing import Any

_ALIAS_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ALIAS_STOPWORDS = {
    "and",
    "conflict",
    "direct",
    "escalation",
    "expansion",
    "risk",
    "the",
}


def optional_text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def unique_strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized_values: list[str] = []
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized and normalized not in normalized_values:
                normalized_values.append(normalized)
    return normalized_values


def trend_list_field(trend: Any, field_name: str) -> list[str]:
    attr_values = unique_strings(getattr(trend, field_name, []))
    if attr_values:
        return attr_values
    definition = getattr(trend, "definition", None)
    if not isinstance(definition, dict):
        return []
    return unique_strings(definition.get(field_name, []))


def canonical_trend_id(
    raw_trend_id: str,
    *,
    trends: list[Any],
    trend_identifier: Callable[[Any], str],
) -> str | None:
    expected_ids = {trend_identifier(trend) for trend in trends}
    if raw_trend_id in expected_ids:
        return raw_trend_id

    raw_tokens = _alias_tokens(raw_trend_id)
    if len(raw_tokens) < 2:
        return None

    matches = [
        trend_identifier(trend)
        for trend in trends
        if len(raw_tokens & _trend_alias_tokens(trend, trend_identifier)) >= 2
    ]
    if len(set(matches)) == 1:
        return matches[0]
    return None


def strict_response_format(
    base_format: dict[str, Any],
    *,
    items: list[Any],
    trends: list[Any],
    trend_identifier: Callable[[Any], str],
) -> dict[str, Any]:
    schema = copy.deepcopy(base_format["json_schema"]["schema"])
    item_ids = [str(item.id) for item in items]
    trend_ids = [trend_identifier(trend) for trend in trends]
    item_output_schema = schema["$defs"].get("_ItemOutput") or schema["$defs"]["ItemOutput"]
    score_output_schema = (
        schema["$defs"].get("_TrendScoreOutput") or schema["$defs"]["TrendScoreOutput"]
    )
    item_output_schema["properties"]["item_id"]["enum"] = item_ids
    score_output_schema["properties"]["trend_id"]["enum"] = trend_ids
    schema["properties"]["items"]["minItems"] = len(item_ids)
    schema["properties"]["items"]["maxItems"] = len(item_ids)
    return {
        "type": "json_schema",
        "json_schema": {"name": "tier1_classification", "schema": schema, "strict": True},
    }


def normalize_output_payload(parsed: object) -> object:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        return parsed
    items: list[dict[str, Any]] = []
    for row in parsed["items"]:
        if not isinstance(row, dict):
            continue
        normalized_row = dict(row)
        normalized_row["trend_scores"] = _normalized_score_rows(row.get("trend_scores"))
        items.append(normalized_row)
    return {"items": items}


def _normalized_score_rows(raw_scores: object) -> list[dict[str, Any]]:
    if not isinstance(raw_scores, list):
        return []
    rows: list[dict[str, Any]] = []
    for score in raw_scores:
        if not isinstance(score, dict):
            continue
        if "trend_id" in score and "relevance_score" in score:
            rows.append(score)
            continue
        rows.extend(_normalized_score_rows(score.get("trend_scores")))
    return rows


def _trend_alias_tokens(trend: Any, trend_identifier: Callable[[Any], str]) -> set[str]:
    values = [trend_identifier(trend), getattr(trend, "name", "")]
    description = getattr(trend, "description", None)
    if isinstance(description, str):
        values.append(description)
    return set().union(*(_alias_tokens(value) for value in values))


def _alias_tokens(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    tokens = {
        _normalize_alias_token(token)
        for token in _ALIAS_TOKEN_RE.findall(value.lower())
        if token not in _ALIAS_STOPWORDS
    }
    return {token for token in tokens if len(token) > 1}


def _normalize_alias_token(alias_part: str) -> str:
    if alias_part == "european":
        return "europe"
    return alias_part
