from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.processing.corroboration_provenance as provenance_module
from src.processing.corroboration_provenance import (
    EventSourceProvenance,
    fallback_event_provenance_summary,
    parse_event_provenance_row,
    refresh_event_provenance,
    refresh_events_for_source,
    summarize_event_provenance,
)
from src.storage.models import Event

pytestmark = pytest.mark.unit


def _observation(
    *,
    source_name: str,
    source_url: str,
    reporting_type: str,
    item_url: str | None = None,
    title: str = "Forces moved near the eastern border overnight",
    author: str | None = None,
    content_hash: str | None = None,
) -> EventSourceProvenance:
    return EventSourceProvenance(
        source_id=uuid4(),
        source_name=source_name,
        source_url=source_url,
        source_tier="major",
        reporting_type=reporting_type,
        item_url=item_url,
        title=title,
        author=author,
        content_hash=content_hash,
    )


def test_summarize_event_provenance_collapses_syndicated_wire_copy() -> None:
    observations = [
        _observation(
            source_name="Regional Outlet A",
            source_url="https://a.example.test",
            reporting_type="secondary",
            author="Reuters staff",
            content_hash="a" * 64,
        ),
        _observation(
            source_name="Regional Outlet B",
            source_url="https://b.example.test",
            reporting_type="secondary",
            author="Reuters",
            content_hash="a" * 64,
        ),
        _observation(
            source_name="Independent Paper",
            source_url="https://independent.example.test",
            reporting_type="secondary",
            author="Staff reporter",
            content_hash="b" * 64,
        ),
    ]

    summary = summarize_event_provenance(
        observations=observations,
        raw_source_count=3,
        unique_source_count=3,
    )

    assert summary.method == "provenance_aware"
    assert summary.independent_evidence_count == 2
    assert summary.weighted_corroboration_score == pytest.approx(1.2)
    assert summary.syndication_group_count == 1


def test_summarize_event_provenance_collapses_reposted_channel_content() -> None:
    observations = [
        _observation(
            source_name="Channel A",
            source_url="https://t.me/channel-a",
            reporting_type="secondary",
            content_hash="c" * 64,
        ),
        _observation(
            source_name="Channel B",
            source_url="https://t.me/channel-b",
            reporting_type="secondary",
            content_hash="c" * 64,
        ),
        _observation(
            source_name="Channel C",
            source_url="https://t.me/channel-c",
            reporting_type="secondary",
            content_hash="d" * 64,
        ),
    ]

    summary = summarize_event_provenance(
        observations=observations,
        raw_source_count=3,
        unique_source_count=3,
    )

    assert summary.independent_evidence_count == 2
    assert summary.near_duplicate_group_count == 1


def test_summarize_event_provenance_keeps_distinct_telegram_channels_independent() -> None:
    observations = [
        _observation(
            source_name="Channel A",
            source_url="https://t.me/channel_a",
            item_url="https://t.me/channel_a/111",
            reporting_type="secondary",
            title="Channel A reported artillery fire near the frontier overnight",
            content_hash=None,
        ),
        _observation(
            source_name="Channel B",
            source_url="https://t.me/channel_b",
            item_url="https://t.me/channel_b/222",
            reporting_type="secondary",
            title="Channel B reported checkpoint closures near the frontier overnight",
            content_hash=None,
        ),
    ]

    summary = summarize_event_provenance(
        observations=observations,
        raw_source_count=2,
        unique_source_count=2,
    )

    assert summary.independent_evidence_count == 2
    assert {group["key"] for group in summary.groups} == {
        "family:t.me/channel_a",
        "family:t.me/channel_b",
    }


def test_summarize_event_provenance_keeps_distinct_firsthand_sources_independent() -> None:
    observations = [
        _observation(
            source_name="Official Statement A",
            source_url="https://gov-a.example.test",
            reporting_type="firsthand",
            content_hash="e" * 64,
        ),
        _observation(
            source_name="Official Statement B",
            source_url="https://gov-b.example.test",
            reporting_type="firsthand",
            content_hash="f" * 64,
        ),
        _observation(
            source_name="Official Statement C",
            source_url="https://gov-c.example.test",
            reporting_type="firsthand",
            content_hash="g" * 64,
        ),
    ]

    summary = summarize_event_provenance(
        observations=observations,
        raw_source_count=3,
        unique_source_count=3,
    )

    assert summary.independent_evidence_count == 3
    assert summary.weighted_corroboration_score == pytest.approx(3.0)


def test_parse_event_provenance_row_supports_mapping_rows() -> None:
    source_id = uuid4()
    parsed = parse_event_provenance_row(
        type(
            "_Row",
            (),
            {
                "_mapping": {
                    "source_id": source_id,
                    "source_name": "Reuters",
                    "source_url": "https://www.reuters.com",
                    "source_tier": "wire",
                    "reporting_type": "secondary",
                    "item_url": "https://example.test/story",
                    "title": "Story title",
                    "author": "Reuters staff",
                    "content_hash": "f" * 64,
                }
            },
        )()
    )

    assert parsed is not None
    assert parsed.source_id == source_id
    assert parsed.reporting_type == "secondary"


def test_fallback_event_provenance_summary_uses_legacy_counts() -> None:
    summary = fallback_event_provenance_summary(
        raw_source_count=4,
        unique_source_count=2,
        reason="migration_backfill",
    )

    assert summary.method == "fallback"
    assert summary.independent_evidence_count == 2
    assert summary.weighted_corroboration_score == pytest.approx(2.0)


def test_provenance_helpers_cover_fallback_and_internal_normalization_paths() -> None:
    empty_summary = summarize_event_provenance(
        observations=[],
        raw_source_count=0,
        unique_source_count=0,
    )
    assert empty_summary.reason == "no_event_item_provenance"

    truncated_summary = provenance_module.EventProvenanceSummary(
        method="provenance_aware",
        reason="test",
        raw_source_count=1,
        unique_source_count=1,
        independent_evidence_count=1,
        weighted_corroboration_score=1.0,
        source_family_count=0,
        syndication_group_count=0,
        near_duplicate_group_count=0,
        groups=(),
        groups_truncated=2,
    )
    assert truncated_summary.as_dict()["groups_truncated"] == 2

    tuple_row = (
        uuid4(),
        "Reuters",
        "https://www.reuters.com",
        "wire",
        "aggregator",
        "https://example.test/story",
        "Title",
        "Author",
        "a" * 64,
    )
    parsed_tuple = parse_event_provenance_row(tuple_row)
    assert parsed_tuple is not None
    assert parsed_tuple.reporting_type == "aggregator"
    assert parse_event_provenance_row((None, "a", "b", "c", "d", "e", "f", "g", "h")) is None
    assert parse_event_provenance_row(object()) is None
    assert (
        parse_event_provenance_row(type("_Row", (), {"_mapping": {"source_name": "x"}})()) is None
    )

    source_family_only = _observation(
        source_name="Outlet Name",
        source_url="https://www.family.example.test",
        reporting_type="secondary",
        title="Short title",
        content_hash=None,
        author=None,
    )
    family_summary = summarize_event_provenance(
        observations=[source_family_only],
        raw_source_count=1,
        unique_source_count=1,
    )
    assert family_summary.groups[0]["key"] == "family:family.example.test"

    source_only_summary = summarize_event_provenance(
        observations=[
            EventSourceProvenance(
                source_id=uuid4(),
                source_name="!!!",
                source_url=None,
                source_tier="regional",
                reporting_type="secondary",
                item_url=None,
                title="tiny",
                author=None,
                content_hash=None,
            )
        ],
        raw_source_count=1,
        unique_source_count=1,
    )
    assert source_only_summary.groups[0]["key"].startswith("source:")

    source_slug = provenance_module.infer_source_family(
        EventSourceProvenance(
            source_id=uuid4(),
            source_name="Telegram Mirror",
            source_url=None,
            source_tier="regional",
            reporting_type="secondary",
            item_url=None,
            title=None,
            author=None,
            content_hash=None,
        )
    )
    assert source_slug == "telegram-mirror"

    long_title_observation = _observation(
        source_name="Long Title Outlet",
        source_url="https://long.example.test",
        reporting_type="secondary",
        title="This is a sufficiently long title to produce a fingerprint",
        content_hash=None,
    )
    long_title_summary = summarize_event_provenance(
        observations=[long_title_observation],
        raw_source_count=1,
        unique_source_count=1,
    )
    assert long_title_summary.groups[0]["key"].startswith("family:long.example.test")


def test_provenance_helper_normalization_paths() -> None:
    assert provenance_module.reporting_type_weight("aggregator") == pytest.approx(0.35)
    assert provenance_module.reporting_type_weight("other") == pytest.approx(0.5)
    assert provenance_module._maybe_str(7) == "7"
    assert (
        provenance_module._normalized_hostname("https://www.example.test/story") == "example.test"
    )
    assert provenance_module._normalized_hostname("example.test") == "example.test"
    assert provenance_module._normalized_hostname(None) is None
    assert (
        provenance_module._source_family_key_from_url("https://t.me/channel_name/123")
        == "t.me/channel_name"
    )
    assert provenance_module._source_family_key_from_url("https://t.me") == "t.me"
    assert provenance_module._slug_text(None) is None
    assert provenance_module._slug_text("   !!!   ") is None
    assert provenance_module._normalized_text(None) == ""
    assert provenance_module._normalized_text(" Mixed   CASE ") == "mixed case"
    assert provenance_module._normalized_value(None) is None


def test_provenance_helper_provider_and_reporting_paths() -> None:
    assert (
        provenance_module._syndication_provider(
            EventSourceProvenance(
                source_id=uuid4(),
                source_name=None,
                source_url=None,
                source_tier=None,
                reporting_type=None,
                item_url=None,
                title=None,
                author=None,
                content_hash=None,
            )
        )
        is None
    )
    summary_without_reporting = summarize_event_provenance(
        observations=[
            EventSourceProvenance(
                source_id=uuid4(),
                source_name="No Reporting Type",
                source_url=None,
                source_tier="regional",
                reporting_type=None,
                item_url=None,
                title="Another sufficiently long title for grouping fallback",
                author=None,
                content_hash=None,
            )
        ],
        raw_source_count=1,
        unique_source_count=1,
    )
    assert summary_without_reporting.groups[0]["reporting_types"] == []


@pytest.mark.asyncio
async def test_refresh_event_provenance_persists_summary(mock_db_session) -> None:
    first_source_id = uuid4()
    second_source_id = uuid4()
    mock_db_session.execute.return_value = SimpleNamespace(
        all=lambda: [
            (
                first_source_id,
                "Regional Outlet A",
                "https://a.example.test",
                "major",
                "secondary",
                "https://a.example.test/story",
                "Forces moved near the eastern border overnight",
                "Reuters staff",
                "a" * 64,
            ),
            (
                second_source_id,
                "Regional Outlet B",
                "https://b.example.test",
                "major",
                "secondary",
                "https://b.example.test/story",
                "Forces moved near the eastern border overnight",
                "Reuters",
                "a" * 64,
            ),
        ]
    )
    event = Event(
        id=uuid4(),
        canonical_summary="Event",
        source_count=2,
        unique_source_count=2,
    )

    summary = await refresh_event_provenance(session=mock_db_session, event=event)

    assert summary.method == "provenance_aware"
    assert summary.independent_evidence_count == 1
    assert event.corroboration_mode == "provenance_aware"
    assert event.provenance_summary["independent_evidence_count"] == 1


@pytest.mark.asyncio
async def test_refresh_events_for_source_recomputes_linked_events(mock_db_session) -> None:
    first_event = Event(
        id=uuid4(),
        canonical_summary="First",
        source_count=1,
        unique_source_count=1,
        lifecycle_status="emerging",
    )
    second_event = Event(
        id=uuid4(),
        canonical_summary="Second",
        source_count=2,
        unique_source_count=2,
        lifecycle_status="emerging",
    )
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [first_event, second_event])
    refresh_mock = AsyncMock(side_effect=_fake_refresh_event_provenance)

    original_refresh = provenance_module.refresh_event_provenance
    provenance_module.refresh_event_provenance = refresh_mock
    try:
        refreshed = await refresh_events_for_source(session=mock_db_session, source_id=uuid4())
    finally:
        provenance_module.refresh_event_provenance = original_refresh

    assert refreshed == 2
    assert refresh_mock.await_count == 2
    assert first_event.epistemic_state == "confirmed"
    assert first_event.lifecycle_status == "confirmed"
    assert second_event.epistemic_state == "emerging"


@pytest.mark.asyncio
async def test_refresh_events_for_source_returns_zero_when_source_is_missing() -> None:
    refreshed = await refresh_events_for_source(session=AsyncMock(), source_id=None)

    assert refreshed == 0


async def _fake_refresh_event_provenance(*, session, event):  # type: ignore[no-untyped-def]
    del session
    event.independent_evidence_count = 3 if event.canonical_summary == "First" else 1
    return fallback_event_provenance_summary(
        raw_source_count=event.source_count,
        unique_source_count=event.unique_source_count,
        reason="test",
    )
