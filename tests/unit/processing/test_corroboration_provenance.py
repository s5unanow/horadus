from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.processing.corroboration_provenance as provenance_module
import src.processing.corroboration_refresh_support as refresh_support_module
from src.processing.corroboration_provenance import (
    EventSourceProvenance,
    fallback_event_provenance_summary,
    parse_event_provenance_row,
    refresh_event_provenance,
    refresh_events_for_source,
    summarize_event_provenance,
)
from src.storage.models import Event, RawItem

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
    assert (
        provenance_module._source_family_key_from_url("https://t.me/s/channel_name/123")
        == "t.me/channel_name"
    )
    assert (
        provenance_module._source_family_key_from_url("https://telegram.me/channel_name/123")
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
async def test_refresh_support_loaders_cover_snapshot_and_item_queries(mock_db_session) -> None:
    trend_id = uuid4()
    first_event_id = uuid4()
    second_event_id = uuid4()
    first_seen = datetime.now(tz=UTC)
    second_seen = datetime.now(tz=UTC)
    raw_item = RawItem(id=uuid4(), title="Item", raw_content="Body")
    mock_db_session.execute.return_value = SimpleNamespace(
        all=lambda: [
            (trend_id, "signal", first_event_id, first_seen),
            (trend_id, "signal", uuid4(), None),
            (trend_id, "signal", second_event_id, second_seen),
        ]
    )
    mock_db_session.scalar.return_value = raw_item

    snapshot = await refresh_support_module._load_novelty_snapshot_for_refresh(
        session=mock_db_session
    )
    missing_item = await refresh_support_module._load_item_for_refresh(
        session=mock_db_session,
        item_id=None,
    )
    loaded_item = await refresh_support_module._load_item_for_refresh(
        session=mock_db_session,
        item_id=raw_item.id,
    )

    assert snapshot == {
        (trend_id, "signal"): ((first_event_id, first_seen), (second_event_id, second_seen))
    }
    assert missing_item is None
    assert loaded_item is raw_item


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
    mock_db_session.execute.return_value = SimpleNamespace(all=list)
    refresh_mock = AsyncMock(side_effect=_fake_refresh_event_provenance)
    refresh_primary_mock = AsyncMock()
    refresh_trends_mock = AsyncMock(return_value=(1, 1))
    load_trends_mock = AsyncMock(return_value=[])
    load_novelty_snapshot_mock = AsyncMock(return_value={})
    call_order: list[tuple[str, str]] = []

    async def wrapped_refresh_event_provenance(*, session, event):  # type: ignore[no-untyped-def]
        call_order.append(("provenance", event.canonical_summary))
        return await refresh_mock(session=session, event=event)

    async def wrapped_refresh_primary(*, session, event):  # type: ignore[no-untyped-def]
        call_order.append(("primary", event.canonical_summary))
        await refresh_primary_mock(session=session, event=event)

    async def wrapped_refresh_trends(  # type: ignore[no-untyped-def]
        *,
        session,
        event,
        trends=None,
        novelty_snapshot=None,
    ):
        call_order.append(("trends", event.canonical_summary))
        assert trends == []
        assert novelty_snapshot == {}
        return await refresh_trends_mock(session=session, event=event)

    original_refresh = provenance_module.refresh_event_provenance
    original_refresh_primary = provenance_module._refresh_event_primary_item
    original_refresh_trends = provenance_module._refresh_event_trend_impacts
    original_load_trends = provenance_module._load_active_trends_for_refresh
    original_load_novelty_snapshot = provenance_module._load_novelty_snapshot_for_refresh
    provenance_module.refresh_event_provenance = wrapped_refresh_event_provenance
    provenance_module._refresh_event_primary_item = wrapped_refresh_primary
    provenance_module._refresh_event_trend_impacts = wrapped_refresh_trends
    provenance_module._load_active_trends_for_refresh = load_trends_mock
    provenance_module._load_novelty_snapshot_for_refresh = load_novelty_snapshot_mock
    try:
        refreshed = await refresh_events_for_source(session=mock_db_session, source_id=uuid4())
    finally:
        provenance_module.refresh_event_provenance = original_refresh
        provenance_module._refresh_event_primary_item = original_refresh_primary
        provenance_module._refresh_event_trend_impacts = original_refresh_trends
        provenance_module._load_active_trends_for_refresh = original_load_trends
        provenance_module._load_novelty_snapshot_for_refresh = original_load_novelty_snapshot

    assert refreshed == 2
    load_trends_mock.assert_awaited_once_with(session=mock_db_session)
    load_novelty_snapshot_mock.assert_awaited_once_with(session=mock_db_session)
    assert refresh_mock.await_count == 2
    assert refresh_primary_mock.await_count == 2
    assert refresh_trends_mock.await_count == 2
    assert call_order == [
        ("provenance", "First"),
        ("primary", "First"),
        ("trends", "First"),
        ("provenance", "Second"),
        ("primary", "Second"),
        ("trends", "Second"),
    ]
    assert first_event.epistemic_state == "confirmed"
    assert first_event.lifecycle_status == "confirmed"
    assert second_event.epistemic_state == "emerging"


@pytest.mark.asyncio
async def test_refresh_events_for_source_returns_zero_when_source_is_missing() -> None:
    refreshed = await refresh_events_for_source(session=AsyncMock(), source_id=None)

    assert refreshed == 0


@pytest.mark.asyncio
async def test_refresh_event_primary_item_reselects_most_credible_item(mock_db_session) -> None:
    candidate_item = RawItem(
        id=uuid4(),
        title=" Fresh canonical summary ",
        raw_content="ignored",
    )
    current_primary = RawItem(
        id=uuid4(),
        title="Current summary",
        raw_content="ignored",
    )
    event = Event(
        id=uuid4(),
        canonical_summary="Old summary",
        primary_item_id=current_primary.id,
        source_count=2,
        unique_source_count=2,
    )
    original_load_candidate = provenance_module._load_most_credible_event_item_for_refresh
    original_load_item = provenance_module._load_item_for_refresh
    original_load_credibility = provenance_module._load_item_effective_credibility_for_refresh
    provenance_module._load_most_credible_event_item_for_refresh = AsyncMock(
        return_value=candidate_item
    )
    provenance_module._load_item_for_refresh = AsyncMock(return_value=current_primary)
    provenance_module._load_item_effective_credibility_for_refresh = AsyncMock(
        side_effect=[0.9, 0.7]
    )
    try:
        await provenance_module._refresh_event_primary_item(
            session=mock_db_session,
            event=event,
        )
    finally:
        provenance_module._load_most_credible_event_item_for_refresh = original_load_candidate
        provenance_module._load_item_for_refresh = original_load_item
        provenance_module._load_item_effective_credibility_for_refresh = original_load_credibility

    assert event.primary_item_id == candidate_item.id
    assert event.canonical_summary == "Fresh canonical summary"


@pytest.mark.asyncio
async def test_refresh_event_primary_item_skips_events_without_ids(mock_db_session) -> None:
    event = Event(
        canonical_summary="Old summary",
        source_count=1,
        unique_source_count=1,
    )

    await provenance_module._refresh_event_primary_item(
        session=mock_db_session,
        event=event,
    )

    mock_db_session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_event_primary_item_skips_missing_query_results(mock_db_session) -> None:
    event = Event(
        id=uuid4(),
        canonical_summary="Old summary",
        primary_item_id=uuid4(),
        source_count=1,
        unique_source_count=1,
    )
    mock_db_session.scalar.return_value = SimpleNamespace(id=None)

    await provenance_module._refresh_event_primary_item(
        session=mock_db_session,
        event=event,
    )

    assert event.canonical_summary == "Old summary"


@pytest.mark.asyncio
async def test_refresh_event_primary_item_uses_candidate_when_current_primary_is_missing(
    mock_db_session,
) -> None:
    candidate_item = RawItem(
        id=uuid4(),
        title="Candidate summary",
        raw_content="ignored",
    )
    event = Event(
        id=uuid4(),
        canonical_summary="Old summary",
        primary_item_id=uuid4(),
        source_count=2,
        unique_source_count=2,
    )
    original_load_candidate = provenance_module._load_most_credible_event_item_for_refresh
    original_load_item = provenance_module._load_item_for_refresh
    provenance_module._load_most_credible_event_item_for_refresh = AsyncMock(
        return_value=candidate_item
    )
    provenance_module._load_item_for_refresh = AsyncMock(return_value=None)
    try:
        await provenance_module._refresh_event_primary_item(
            session=mock_db_session,
            event=event,
        )
    finally:
        provenance_module._load_most_credible_event_item_for_refresh = original_load_candidate
        provenance_module._load_item_for_refresh = original_load_item

    assert event.primary_item_id == candidate_item.id
    assert event.canonical_summary == "Candidate summary"


@pytest.mark.asyncio
async def test_refresh_event_primary_item_preserves_current_primary_on_credibility_tie(
    mock_db_session,
) -> None:
    candidate_item = RawItem(
        id=uuid4(),
        title="Candidate summary",
        raw_content="ignored",
    )
    current_primary = RawItem(
        id=uuid4(),
        title=" Current summary ",
        raw_content="ignored",
    )
    event = Event(
        id=uuid4(),
        canonical_summary="Old summary",
        primary_item_id=current_primary.id,
        source_count=2,
        unique_source_count=2,
    )
    original_load_candidate = provenance_module._load_most_credible_event_item_for_refresh
    original_load_item = provenance_module._load_item_for_refresh
    original_load_credibility = provenance_module._load_item_effective_credibility_for_refresh
    provenance_module._load_most_credible_event_item_for_refresh = AsyncMock(
        return_value=candidate_item
    )
    provenance_module._load_item_for_refresh = AsyncMock(return_value=current_primary)
    provenance_module._load_item_effective_credibility_for_refresh = AsyncMock(
        side_effect=[0.8, 0.8]
    )
    try:
        await provenance_module._refresh_event_primary_item(
            session=mock_db_session,
            event=event,
        )
    finally:
        provenance_module._load_most_credible_event_item_for_refresh = original_load_candidate
        provenance_module._load_item_for_refresh = original_load_item
        provenance_module._load_item_effective_credibility_for_refresh = original_load_credibility

    assert event.primary_item_id == current_primary.id
    assert event.canonical_summary == "Current summary"


def test_build_canonical_summary_falls_back_to_trimmed_raw_content() -> None:
    item = RawItem(
        title="   ",
        raw_content=f"  {'x' * 450}  ",
    )

    summary = provenance_module._build_canonical_summary(item)

    assert summary == "x" * 400


@pytest.mark.asyncio
async def test_refresh_event_trend_impacts_skips_when_no_active_trends(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Event", source_count=1, unique_source_count=1)
    load_trends_mock = AsyncMock(return_value=[])
    reconcile_mock = AsyncMock(return_value=(9, 9))
    monkeypatch.setattr(provenance_module, "_load_active_trends_for_refresh", load_trends_mock)
    monkeypatch.setattr(provenance_module, "reconcile_event_trend_impacts", reconcile_mock)

    refreshed = await provenance_module._refresh_event_trend_impacts(
        session=mock_db_session,
        event=event,
    )

    assert refreshed == (0, 0)
    reconcile_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_event_trend_impacts_reconciles_active_trends(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Event", source_count=1, unique_source_count=1)
    trend = object()
    load_trends_mock = AsyncMock(return_value=[trend])

    async def fake_reconcile(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["trends"] == [trend]
        assert await kwargs["load_event_source_credibility"](event) == pytest.approx(0.8)
        assert await kwargs["load_corroboration_score"](event) == pytest.approx(1.0)
        assert await kwargs["load_novelty_score"](
            trend_id=uuid4(),
            signal_type="signal",
            event_id=event.id,
        ) == pytest.approx(0.33)
        assert await kwargs["capture_taxonomy_gap"]() is None
        return (2, 1)

    def trend_engine_factory(*, session):  # type: ignore[no-untyped-def]
        return SimpleNamespace(session=session)

    monkeypatch.setattr(provenance_module, "_load_active_trends_for_refresh", load_trends_mock)
    monkeypatch.setattr(
        provenance_module,
        "_load_event_source_credibility_for_refresh",
        AsyncMock(return_value=0.8),
    )
    monkeypatch.setattr(
        provenance_module,
        "_load_novelty_score_for_refresh",
        AsyncMock(return_value=0.33),
    )
    monkeypatch.setattr(provenance_module, "reconcile_event_trend_impacts", fake_reconcile)
    monkeypatch.setattr(provenance_module, "TrendEngine", trend_engine_factory)

    refreshed = await provenance_module._refresh_event_trend_impacts(
        session=mock_db_session,
        event=event,
    )

    assert refreshed == (2, 1)


@pytest.mark.asyncio
async def test_refresh_event_trend_impacts_uses_supplied_trends_without_reloading(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id=uuid4(), canonical_summary="Event", source_count=1, unique_source_count=1)
    trend = object()

    async def fake_reconcile(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["trends"] == [trend]
        assert await kwargs["load_novelty_score"](
            trend_id=uuid4(),
            signal_type="signal",
            event_id=event.id,
        ) == pytest.approx(0.24)
        return (1, 1)

    load_trends_mock = AsyncMock(side_effect=AssertionError("should not reload trends"))
    monkeypatch.setattr(provenance_module, "_load_active_trends_for_refresh", load_trends_mock)
    monkeypatch.setattr(
        provenance_module,
        "_load_event_source_credibility_for_refresh",
        AsyncMock(return_value=0.8),
    )
    monkeypatch.setattr(
        provenance_module,
        "_load_novelty_score_for_refresh",
        AsyncMock(return_value=0.24),
    )
    monkeypatch.setattr(provenance_module, "reconcile_event_trend_impacts", fake_reconcile)
    monkeypatch.setattr(
        provenance_module,
        "TrendEngine",
        lambda *, session: SimpleNamespace(session=session),
    )

    refreshed = await provenance_module._refresh_event_trend_impacts(
        session=mock_db_session,
        event=event,
        trends=[trend],
        novelty_snapshot={},
    )

    assert refreshed == (1, 1)


@pytest.mark.asyncio
async def test_load_active_trends_for_refresh_returns_session_scalars(mock_db_session) -> None:
    trend = object()
    mock_db_session.scalars.return_value = SimpleNamespace(all=lambda: [trend])

    loaded = await provenance_module._load_active_trends_for_refresh(session=mock_db_session)

    assert loaded == [trend]


@pytest.mark.asyncio
async def test_load_event_source_credibility_for_refresh_handles_missing_and_invalid_values(
    mock_db_session,
) -> None:
    missing_primary = Event(canonical_summary="Missing", source_count=1, unique_source_count=1)
    assert await provenance_module._load_event_source_credibility_for_refresh(
        session=mock_db_session,
        event=missing_primary,
    ) == pytest.approx(provenance_module.DEFAULT_SOURCE_CREDIBILITY)

    event = Event(
        canonical_summary="Credibility",
        source_count=1,
        unique_source_count=1,
        primary_item_id=uuid4(),
    )
    mock_db_session.scalar.side_effect = [0.85, "bad"]

    assert await provenance_module._load_event_source_credibility_for_refresh(
        session=mock_db_session,
        event=event,
    ) == pytest.approx(0.85)
    assert await provenance_module._load_event_source_credibility_for_refresh(
        session=mock_db_session,
        event=event,
    ) == pytest.approx(provenance_module.DEFAULT_SOURCE_CREDIBILITY)


@pytest.mark.asyncio
async def test_load_novelty_score_and_taxonomy_gap_helpers_cover_refresh_paths(
    mock_db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_at = object()
    mock_db_session.scalar.return_value = seen_at
    monkeypatch.setattr(
        refresh_support_module,
        "calculate_recency_novelty",
        lambda *, last_seen_at: 0.42 if last_seen_at is seen_at else 0.0,
    )

    score = await provenance_module._load_novelty_score_for_refresh(
        session=mock_db_session,
        trend_id=uuid4(),
        signal_type="signal",
        event_id=uuid4(),
    )

    assert score == pytest.approx(0.42)
    snapshot_score = await provenance_module._load_novelty_score_for_refresh(
        session=mock_db_session,
        trend_id=uuid4(),
        signal_type="signal",
        event_id=uuid4(),
        snapshot={
            (uuid4(), "other"): ((uuid4(), datetime.now(tz=UTC)),),
            (uuid4(), "signal"): (),
        },
    )
    assert snapshot_score == pytest.approx(0.0)
    snapshot_trend_id = uuid4()
    current_event_id = uuid4()
    other_event_id = uuid4()
    snapshot_score = await provenance_module._load_novelty_score_for_refresh(
        session=mock_db_session,
        trend_id=snapshot_trend_id,
        signal_type="signal",
        event_id=current_event_id,
        snapshot={
            (snapshot_trend_id, "signal"): (
                (current_event_id, datetime.now(tz=UTC)),
                (other_event_id, seen_at),
            )
        },
    )
    assert snapshot_score == pytest.approx(0.42)
    assert await provenance_module._capture_taxonomy_gap_for_refresh() is None


@pytest.mark.asyncio
async def test_load_corroboration_score_for_refresh_applies_penalties() -> None:
    contradiction_graph_event = Event(
        canonical_summary="Graph",
        source_count=1,
        unique_source_count=1,
        corroboration_score=2.0,
        corroboration_mode="provenance_aware",
        extracted_claims={"claim_graph": {"links": [{"relation": "contradict"}]}},
    )
    contradicted_event = Event(
        canonical_summary="Contradicted",
        source_count=1,
        unique_source_count=1,
        corroboration_score=2.0,
        corroboration_mode="provenance_aware",
        has_contradictions=True,
    )
    malformed_graph_event = Event(
        canonical_summary="Malformed",
        source_count=1,
        unique_source_count=1,
        corroboration_score=2.0,
        corroboration_mode="provenance_aware",
        extracted_claims={"claim_graph": {"links": "not-a-list"}},
    )
    calm_event = Event(
        canonical_summary="Calm",
        source_count=1,
        unique_source_count=1,
        corroboration_score=2.0,
        corroboration_mode="provenance_aware",
    )

    assert await provenance_module._load_corroboration_score_for_refresh(
        contradiction_graph_event
    ) == pytest.approx(1.7)
    assert await provenance_module._load_corroboration_score_for_refresh(
        contradicted_event
    ) == pytest.approx(1.4)
    assert await provenance_module._load_corroboration_score_for_refresh(
        malformed_graph_event
    ) == pytest.approx(2.0)
    assert await provenance_module._load_corroboration_score_for_refresh(
        calm_event
    ) == pytest.approx(2.0)


async def _fake_refresh_event_provenance(*, session, event):  # type: ignore[no-untyped-def]
    del session
    event.independent_evidence_count = 3 if event.canonical_summary == "First" else 1
    event.corroboration_mode = "provenance_aware"
    return fallback_event_provenance_summary(
        raw_source_count=event.source_count,
        unique_source_count=event.unique_source_count,
        reason="test",
    )
