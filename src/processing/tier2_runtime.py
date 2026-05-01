"""Shared Tier-2 output parsing/persistence helpers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.processing.entity_registry import sync_event_entities
from src.storage.event_extraction import promote_canonical_extraction

_PARTIAL_YEAR_RE = re.compile(r"^\d{4}$")
_PARTIAL_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_MARKETING_YEAR_RE = re.compile(r"^(?P<start>\d{4})/(?P<end>\d{2}|\d{4})$")
_MONTH_SLASH_RANGE_RE = re.compile(r"^(?P<start>\d{4}-\d{2})/\d{4}-\d{2}$")
_DATE_SLASH_RANGE_RE = re.compile(r"^(?P<start>\d{4}-\d{2}-\d{2})/\d{4}-\d{2}-\d{2}$")
_YEAR_RANGE_RE = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{4})$")
_QUALIFIED_YEAR_RE = re.compile(r"^(?P<qualifier>early|mid|late)[\s-]+(?P<year>\d{4})$")
_DATE_RANGE_SEPARATORS = (" to ", " through ", " until ", " - ", " \u2013 ", " \u2014 ")
_QUALIFIER_MONTHS = {"early": 1, "mid": 6, "late": 10}


class Tier2Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    entity_type: str = Field(pattern="^(person|organization|location|event)$")
    role: str = Field(pattern="^(actor|location)$")

    @model_validator(mode="after")
    def _validate_role(self) -> Tier2Entity:
        if self.role == "location" and self.entity_type == "event":
            self.entity_type = "location"
        if self.role == "location" and self.entity_type == "organization":
            self.entity_type = "location"
        if self.role == "location" and self.entity_type != "location":
            msg = "Location-role entities must use entity_type='location'"
            raise ValueError(msg)
        if self.role == "actor" and self.entity_type not in {
            "person",
            "organization",
            "location",
        }:
            msg = "Actor-role entities must use entity_type='person', 'organization', or 'location'"
            raise ValueError(msg)
        return self


class Tier2Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    extracted_who: list[str] = Field(default_factory=list)
    extracted_what: str = Field(min_length=1)
    extracted_where: str | None = None
    extracted_when: str | None = None
    claims: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    entities: list[Tier2Entity] = Field(default_factory=list)
    has_contradictions: bool = False
    contradiction_notes: str | None = None


def parse_tier2_response(response: Any, *, output_model: Any) -> Any:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        msg = "Tier 2 response missing choices"
        raise ValueError(msg)
    message = getattr(choices[0], "message", None)
    raw_content = getattr(message, "content", None)
    if not isinstance(raw_content, str) or not raw_content.strip():
        msg = "Tier 2 response missing message content"
        raise ValueError(msg)

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        msg = "Tier 2 response is not valid JSON"
        raise ValueError(msg) from exc
    return output_model.model_validate(parsed)


def validate_tier2_output_alignment(output: Any, *, trends: list[Any]) -> None:
    if not trends:
        msg = "At least one trend is required for deterministic trend mapping"
        raise ValueError(msg)
    if not output.claims and not output.extracted_what.strip():
        msg = "Tier 2 output must include extracted_what or at least one claim"
        raise ValueError(msg)


def parse_tier2_output(
    *,
    raw_content: str,
    output_model: Any,
    validate_output_alignment: Any,
    trends: list[Any],
) -> Any | None:
    try:
        output = output_model.model_validate(json.loads(raw_content))
        validate_output_alignment(output, trends=trends)
        return output
    except (ValueError, json.JSONDecodeError):
        return None


def parse_tier2_datetime(raw_value: str | None) -> datetime | None:
    if raw_value is None or not raw_value.strip():
        return None
    normalized = _normalize_tier2_datetime_value(raw_value)
    partial = _parse_partial_tier2_datetime(normalized)
    if partial is not None:
        return partial
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_tier2_datetime_value(raw_value: str) -> str:
    normalized = raw_value.strip().strip(".,;").replace("Z", "+00:00")
    lowered = normalized.lower()
    for prefix in ("since ", "as of ", "by "):
        if lowered.startswith(prefix):
            return normalized[len(prefix) :].strip().strip(".,;")
    for separator in _DATE_RANGE_SEPARATORS:
        if separator in lowered:
            index = lowered.index(separator)
            return normalized[:index].strip().strip(".,;")
    return normalized


def _parse_partial_tier2_datetime(normalized: str) -> datetime | None:
    lowered = normalized.lower()
    if _PARTIAL_YEAR_RE.fullmatch(lowered):
        return datetime(int(lowered), 1, 1, tzinfo=UTC)
    if _PARTIAL_MONTH_RE.fullmatch(lowered):
        year, month = lowered.split("-")
        return datetime(int(year), int(month), 1, tzinfo=UTC)

    marketing_year = _MARKETING_YEAR_RE.fullmatch(lowered)
    if marketing_year is not None:
        return datetime(int(marketing_year.group("start")), 1, 1, tzinfo=UTC)

    month_slash_range = _MONTH_SLASH_RANGE_RE.fullmatch(lowered)
    if month_slash_range is not None:
        year, month = month_slash_range.group("start").split("-")
        return datetime(int(year), int(month), 1, tzinfo=UTC)

    date_slash_range = _DATE_SLASH_RANGE_RE.fullmatch(lowered)
    if date_slash_range is not None:
        return datetime.fromisoformat(date_slash_range.group("start")).replace(tzinfo=UTC)

    year_range = _YEAR_RANGE_RE.fullmatch(lowered)
    if year_range is not None:
        return datetime(int(year_range.group("start")), 1, 1, tzinfo=UTC)

    qualified_year = _QUALIFIED_YEAR_RE.fullmatch(lowered)
    if qualified_year is not None:
        qualifier = qualified_year.group("qualifier")
        return datetime(
            int(qualified_year.group("year")),
            _QUALIFIER_MONTHS[qualifier],
            1,
            tzinfo=UTC,
        )
    return None


async def persist_tier2_output(
    *,
    session: Any,
    sync_event_claims: Any,
    event: Any,
    output: Any,
    trends: list[Any],
    apply_output: Any,
    extraction_provenance: dict[str, Any],
    mapped_impacts_count: Any,
) -> tuple[int, int]:
    apply_output(event=event, output=output, trends=trends)
    await sync_event_entities(session=session, event=event, output=output)
    promote_canonical_extraction(event, extraction_provenance=extraction_provenance)
    await sync_event_claims(session=session, event=event)
    await session.flush()
    return (len(event.categories or []), mapped_impacts_count(event))


def mapped_impacts_count(event: Any) -> int:
    claims = event.extracted_claims if isinstance(event.extracted_claims, dict) else {}
    impacts = claims.get("trend_impacts")
    if not isinstance(impacts, list):
        return 0
    return len(impacts)
