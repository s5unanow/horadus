from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from src.core.config import settings
from src.ingestion.rss_collector import FeedConfig, RSSCollector
from src.storage.models import ProcessingStatus

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_load_config_parses_settings_and_feeds(
    tmp_path: Path,
    mock_db_session,
    mock_http_client,
) -> None:
    config_path = tmp_path / "rss.yaml"
    config_path.write_text(
        """
settings:
  request_timeout_seconds: 42
  user_agent: "test-agent"
  default_check_interval_minutes: 15
  default_max_items_per_fetch: 10
feeds:
  - name: "Feed One"
    url: "https://example.com/rss"
    credibility: 0.9
    enabled: true
  - name: ""
    url: ""
""",
        encoding="utf-8",
    )

    collector = RSSCollector(
        session=mock_db_session,
        http_client=mock_http_client,
        config_path=str(config_path),
    )

    await collector.load_config(force=True)

    assert collector.settings.request_timeout_seconds == 42
    assert collector.settings.user_agent == "test-agent"
    assert len(collector.feeds) == 1
    assert collector.feeds[0].name == "Feed One"
    assert collector.feeds[0].check_interval_minutes == 15
    assert collector.feeds[0].max_items_per_fetch == 10


@pytest.mark.asyncio
async def test_load_config_uses_six_hour_profile_defaults_when_settings_omitted(
    tmp_path: Path,
    mock_db_session,
    mock_http_client,
) -> None:
    config_path = tmp_path / "rss_defaults.yaml"
    config_path.write_text(
        """
feeds:
  - name: "Feed One"
    url: "https://example.com/rss"
    credibility: 0.9
    enabled: true
""",
        encoding="utf-8",
    )

    collector = RSSCollector(
        session=mock_db_session,
        http_client=mock_http_client,
        config_path=str(config_path),
    )

    await collector.load_config(force=True)

    assert collector.feeds[0].max_items_per_fetch == 200


@pytest.mark.asyncio
async def test_collect_feed_counts_stored_and_skipped(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(
        name="Example Feed",
        url="https://example.com/rss",
        credibility=0.8,
        max_items_per_fetch=5,
    )
    source = SimpleNamespace(error_count=0)

    async def fake_get_or_create_source(_feed: FeedConfig) -> SimpleNamespace:
        return source

    async def fake_fetch_feed(_url: str) -> SimpleNamespace:
        return SimpleNamespace(entries=[{"title": "a"}, {"title": "b"}])

    async def fake_process_entry(_source, _feed: FeedConfig, _entry) -> bool:
        return _entry["title"] == "a"

    async def fake_record_success(_source, *, window_end) -> None:
        _ = window_end

    async def fake_record_failure(_source, _error: str) -> None:
        return None

    monkeypatch.setattr(collector, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(collector, "_fetch_feed", fake_fetch_feed)
    monkeypatch.setattr(collector, "_process_entry", fake_process_entry)
    monkeypatch.setattr(collector, "_record_source_success", fake_record_success)
    monkeypatch.setattr(collector, "_record_source_failure", fake_record_failure)

    result = await collector.collect_feed(feed)

    assert result.feed_name == "Example Feed"
    assert result.items_fetched == 2
    assert result.items_stored == 1
    assert result.items_skipped == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_collect_feed_records_source_failure(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(
        name="Broken Feed",
        url="https://example.com/broken",
        credibility=0.8,
    )
    source = SimpleNamespace(error_count=0)
    failure_messages: list[str] = []

    async def fake_get_or_create_source(_feed: FeedConfig) -> SimpleNamespace:
        return source

    async def fake_fetch_feed(_url: str) -> None:
        msg = "timeout"
        raise httpx.ReadTimeout(msg)

    async def fake_record_failure(_source, error: str) -> None:
        failure_messages.append(error)

    async def fake_record_success(_source, *, window_end) -> None:
        _ = window_end

    monkeypatch.setattr(collector, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(collector, "_fetch_feed", fake_fetch_feed)
    monkeypatch.setattr(collector, "_record_source_failure", fake_record_failure)
    monkeypatch.setattr(collector, "_record_source_success", fake_record_success)

    result = await collector.collect_feed(feed)

    assert result.items_stored == 0
    assert len(result.errors) == 1
    assert result.transient_errors == 1
    assert result.terminal_errors == 0
    assert result.errors[0].startswith("[transient]")
    assert failure_messages


@pytest.mark.asyncio
async def test_collect_feed_classifies_terminal_failure(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(
        name="Broken Feed",
        url="https://example.com/broken",
        credibility=0.8,
    )
    source = SimpleNamespace(error_count=0)
    failure_messages: list[str] = []

    async def fake_get_or_create_source(_feed: FeedConfig) -> SimpleNamespace:
        return source

    async def fake_fetch_feed(_url: str) -> None:
        msg = "malformed payload"
        raise ValueError(msg)

    async def fake_record_failure(_source, error: str) -> None:
        failure_messages.append(error)

    async def fake_record_success(_source, *, window_end) -> None:
        _ = window_end

    monkeypatch.setattr(collector, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(collector, "_fetch_feed", fake_fetch_feed)
    monkeypatch.setattr(collector, "_record_source_failure", fake_record_failure)
    monkeypatch.setattr(collector, "_record_source_success", fake_record_success)

    result = await collector.collect_feed(feed)

    assert result.items_stored == 0
    assert len(result.errors) == 1
    assert result.transient_errors == 0
    assert result.terminal_errors == 1
    assert result.errors[0].startswith("[terminal]")
    assert failure_messages


@pytest.mark.asyncio
async def test_fetch_with_retries_recovers_after_timeout(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    collector.max_retries = 2
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.text = "<rss></rss>"
    mock_http_client.get = AsyncMock(side_effect=[httpx.ReadTimeout("timeout"), response])
    monkeypatch.setattr(collector.rate_limiter, "wait", AsyncMock(return_value=None))
    monkeypatch.setattr("src.ingestion.rss_collector.asyncio.sleep", AsyncMock(return_value=None))

    result = await collector._fetch_with_retries("https://example.com/rss", timeout_seconds=5)

    assert result == "<rss></rss>"
    assert mock_http_client.get.await_count == 2


@pytest.mark.asyncio
async def test_fetch_with_retries_stops_after_retry_budget(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    collector.max_retries = 1
    mock_http_client.get = AsyncMock(
        side_effect=[httpx.ReadTimeout("timeout"), httpx.ReadTimeout("timeout")]
    )
    monkeypatch.setattr(collector.rate_limiter, "wait", AsyncMock(return_value=None))
    monkeypatch.setattr("src.ingestion.rss_collector.asyncio.sleep", AsyncMock(return_value=None))

    with pytest.raises(httpx.ReadTimeout):
        await collector._fetch_with_retries("https://example.com/rss", timeout_seconds=5)

    assert mock_http_client.get.await_count == 2


def test_normalize_url_removes_tracking_parts() -> None:
    normalized = RSSCollector._normalize_url("https://www.Example.com/path/?utm=1#frag")
    assert normalized == "https://example.com/path"


def test_extract_summary_uses_description_then_content() -> None:
    with_summary = {"description": "from-description"}
    from_content = {"content": [{"value": "from-content"}]}

    assert RSSCollector._extract_summary(with_summary) == "from-description"
    assert RSSCollector._extract_summary(from_content) == "from-content"


@pytest.mark.asyncio
async def test_is_duplicate_checks_recent_window(mock_db_session, mock_http_client) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    mock_db_session.scalar.return_value = uuid4()

    is_duplicate = await collector._is_duplicate(
        normalized_url="https://example.com/article",
        content_hash="abc123",
    )

    assert is_duplicate is True
    assert mock_db_session.scalar.await_count == 1


@pytest.mark.asyncio
async def test_store_item_sets_pending_status(mock_db_session, mock_http_client) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    source = SimpleNamespace(id=uuid4())
    feed = FeedConfig(
        name="Example Feed",
        url="https://example.com/rss",
        credibility=0.8,
        language="en",
    )

    item = await collector._store_item(
        source=source,
        feed=feed,
        entry={"title": "Hello", "author": "A", "language": "en"},
        normalized_url="https://example.com/article",
        title="Hello",
        content="Body",
        content_hash="deadbeef",
    )

    assert item is not None
    assert item.processing_status == ProcessingStatus.PENDING
    assert item.external_id == "https://example.com/article"
    assert mock_db_session.add.call_count == 1


def test_determine_collection_window_first_run_uses_default_lookback(
    mock_db_session,
    mock_http_client,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    now = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)
    source = SimpleNamespace(ingestion_window_end_at=None)

    expected_start, actual_start = collector._determine_collection_window(
        source=source,
        now_utc=now,
    )
    gap_seconds, overlap_seconds = collector._window_coverage_metrics(
        expected_start=expected_start,
        actual_start=actual_start,
    )

    assert expected_start == now - timedelta(hours=12)
    assert actual_start == expected_start
    assert gap_seconds == 0
    assert overlap_seconds == 0


def test_determine_collection_window_uses_overlap_from_watermark(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    watermark = datetime(2026, 2, 15, 6, 0, tzinfo=UTC)
    source = SimpleNamespace(ingestion_window_end_at=watermark)
    monkeypatch.setattr(settings, "INGESTION_WINDOW_OVERLAP_SECONDS", 300)

    expected_start, actual_start = collector._determine_collection_window(
        source=source,
        now_utc=datetime(2026, 2, 16, 12, 0, tzinfo=UTC),
    )
    gap_seconds, overlap_seconds = collector._window_coverage_metrics(
        expected_start=expected_start,
        actual_start=actual_start,
    )

    assert expected_start == watermark
    assert actual_start == watermark - timedelta(seconds=300)
    assert gap_seconds == 0
    assert overlap_seconds == 300
