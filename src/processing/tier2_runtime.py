"""Shared Tier-2 output parsing/persistence helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.processing.entity_registry import sync_event_entities
from src.storage.event_extraction import promote_canonical_extraction


class Tier2Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    entity_type: str = Field(pattern="^(person|organization|location)$")
    role: str = Field(pattern="^(actor|location)$")

    @model_validator(mode="after")
    def _validate_role(self) -> Tier2Entity:
        if self.role == "location" and self.entity_type != "location":
            msg = "Location-role entities must use entity_type='location'"
            raise ValueError(msg)
        if self.role == "actor" and self.entity_type not in {"person", "organization"}:
            msg = "Actor-role entities must use entity_type='person' or 'organization'"
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
    normalized = raw_value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
