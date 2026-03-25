from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def gdelt_provider_source_key(
    *,
    query: str,
    themes: list[str],
    actors: list[str],
    countries: list[str],
    languages: list[str],
) -> str:
    payload = {
        "query": _normalize_text(query) or "",
        "themes": _normalize_list(themes),
        "actors": _normalize_list(actors),
        "countries": _normalize_list(countries),
        "languages": _normalize_list(languages),
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return f"gdelt:{digest}"


def gdelt_provider_source_key_from_mapping(payload: Mapping[str, Any] | None) -> str:
    config = payload or {}
    return gdelt_provider_source_key(
        query=str(config.get("query", "")),
        themes=_coerce_list(config.get("themes")),
        actors=_coerce_list(config.get("actors")),
        countries=_coerce_list(config.get("countries")),
        languages=_coerce_list(config.get("languages")),
    )


def telegram_provider_source_key(channel_ref: str | None) -> str | None:
    handle = normalize_telegram_channel_handle(channel_ref)
    if handle is None:
        return None
    return f"telegram:{handle}"


def normalize_telegram_channel_handle(channel_ref: str | None) -> str | None:
    normalized = _normalize_text(channel_ref)
    if normalized is None:
        return None
    lowered = normalized.lower()
    prefixes = ("@", "https://t.me/", "http://t.me/", "t.me/")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            handle = lowered.removeprefix(prefix).split("/", 1)[0].strip()
            return handle or None
    return None


def _coerce_list(value: Any) -> list[str]:
    return value if isinstance(value, list) else []


def _normalize_list(values: list[str]) -> list[str]:
    normalized_values: set[str] = set()
    for value in values:
        normalized = _normalize_text(value)
        if normalized is not None:
            normalized_values.add(normalized)
    return sorted(normalized_values)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split()).lower()
    return normalized or None
