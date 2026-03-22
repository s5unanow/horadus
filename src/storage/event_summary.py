"""Helpers for canonical-vs-synthesized event summary semantics."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from src.storage.models import Event


def resolved_event_summary(event: Event) -> str:
    """Return the best available event-level summary for display and reuse."""
    for candidate in (event.event_summary, event.canonical_summary):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def event_summary_expression() -> Any:
    """Return the SQL expression for the best available event-level summary."""
    return func.coalesce(
        func.nullif(func.btrim(Event.event_summary), ""),
        Event.canonical_summary,
    )


def refresh_event_summary_from_canonical(
    event: Event,
    *,
    previous_canonical_summary: str | None = None,
) -> None:
    """Keep fallback event summaries aligned until Tier-2 synthesizes one."""
    current_event_summary = (
        event.event_summary.strip() if isinstance(event.event_summary, str) else ""
    )
    previous_canonical = (
        previous_canonical_summary.strip() if isinstance(previous_canonical_summary, str) else ""
    )
    if not current_event_summary or current_event_summary == previous_canonical:
        event.event_summary = event.canonical_summary
