from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

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


def test_normalize_url_preserves_non_tracking_query_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEDUP_URL_QUERY_MODE", "keep_non_tracking")
    monkeypatch.setattr(settings, "DEDUP_URL_TRACKING_PARAM_PREFIXES", ["utm_"])
    monkeypatch.setattr(settings, "DEDUP_URL_TRACKING_PARAMS", ["fbclid"])

    normalized = RSSCollector._normalize_url(
        "https://www.Example.com/path/?b=2&utm_medium=social&a=1&fbclid=xyz"
    )

    assert normalized == "https://example.com/path?a=1&b=2"


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


@pytest.mark.asyncio
async def test_load_config_validates_file_shapes_and_unchanged_mtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_db_session,
    mock_http_client,
) -> None:
    config_path = tmp_path / "rss.yaml"
    config_path.write_text("settings: {}\nfeeds: []\n", encoding="utf-8")
    collector = RSSCollector(
        session=mock_db_session,
        http_client=mock_http_client,
        config_path=str(config_path),
    )

    await collector.load_config(force=True)
    monkeypatch.setattr(collector, "_parse_settings", lambda _raw: pytest.fail("should not parse"))
    monkeypatch.setattr(collector, "_parse_feeds", lambda *_args: pytest.fail("should not parse"))
    await collector.load_config(force=False)

    missing = RSSCollector(
        session=mock_db_session,
        http_client=mock_http_client,
        config_path=str(tmp_path / "missing.yaml"),
    )
    invalid_top_level = tmp_path / "invalid_top_level.yaml"
    invalid_top_level.write_text("- item\n", encoding="utf-8")
    invalid_settings = tmp_path / "invalid_settings.yaml"
    invalid_settings.write_text("settings: []\nfeeds: []\n", encoding="utf-8")
    invalid_feeds = tmp_path / "invalid_feeds.yaml"
    invalid_feeds.write_text("settings: {}\nfeeds: {}\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="RSS config file not found"):
        await missing.load_config()

    with pytest.raises(ValueError, match="expected mapping"):
        await RSSCollector(
            session=mock_db_session,
            http_client=mock_http_client,
            config_path=str(invalid_top_level),
        ).load_config()

    with pytest.raises(ValueError, match="Invalid RSS settings format"):
        await RSSCollector(
            session=mock_db_session,
            http_client=mock_http_client,
            config_path=str(invalid_settings),
        ).load_config()

    with pytest.raises(ValueError, match="Invalid RSS feed list format"):
        await RSSCollector(
            session=mock_db_session,
            http_client=mock_http_client,
            config_path=str(invalid_feeds),
        ).load_config()


@pytest.mark.asyncio
async def test_collect_all_only_collects_enabled_feeds(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    collector._feeds = [
        FeedConfig(name="One", url="https://example.com/1", credibility=0.8, enabled=True),
        FeedConfig(name="Two", url="https://example.com/2", credibility=0.8, enabled=False),
        FeedConfig(name="Three", url="https://example.com/3", credibility=0.8, enabled=True),
    ]
    collected: list[str] = []

    async def fake_load_config(force: bool = False) -> None:
        del force

    async def fake_collect_feed(feed: FeedConfig) -> object:
        collected.append(feed.name)
        return {"feed": feed.name}

    monkeypatch.setattr(collector, "load_config", fake_load_config)
    monkeypatch.setattr(collector, "collect_feed", fake_collect_feed)

    results = await collector.collect_all()

    assert results == [{"feed": "One"}, {"feed": "Three"}]
    assert collected == ["One", "Three"]


@pytest.mark.asyncio
async def test_collect_feed_handles_per_entry_errors_and_empty_timestamps(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(
        name="Example Feed",
        url="https://example.com/rss",
        credibility=0.8,
        max_items_per_fetch=2,
    )
    source = SimpleNamespace(error_count=0)
    recorded_window_end: list[datetime] = []

    async def fake_get_or_create_source(_feed: FeedConfig) -> SimpleNamespace:
        return source

    async def fake_fetch_feed(_url: str) -> SimpleNamespace:
        return SimpleNamespace(entries=[{"title": "a"}, {"title": "b"}])

    async def fake_process_entry(_source, _feed: FeedConfig, entry) -> bool:
        if entry["title"] == "a":
            raise RuntimeError("bad entry")
        return False

    async def fake_record_success(_source, *, window_end: datetime) -> None:
        recorded_window_end.append(window_end)

    monkeypatch.setattr(collector, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(collector, "_fetch_feed", fake_fetch_feed)
    monkeypatch.setattr(collector, "_process_entry", fake_process_entry)
    monkeypatch.setattr(collector, "_record_source_success", fake_record_success)

    before = datetime.now(tz=UTC)
    result = await collector.collect_feed(feed)
    after = datetime.now(tz=UTC)

    assert result.items_fetched == 2
    assert result.items_stored == 0
    assert result.items_skipped == 1
    assert result.errors == ["bad entry"]
    assert len(recorded_window_end) == 1
    assert before <= recorded_window_end[0] <= after


@pytest.mark.asyncio
async def test_process_entry_covers_rejected_duplicate_and_summary_fallback_paths(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    source = SimpleNamespace(id=uuid4())
    feed = FeedConfig(name="Feed", url="https://example.com/rss", credibility=0.8)

    assert await collector._process_entry(source, feed, {"title": "missing link"}) is False

    monkeypatch.setattr(collector, "_normalize_url", lambda _url: None)
    assert await collector._process_entry(source, feed, {"link": "https://example.com"}) is False

    monkeypatch.setattr(collector, "_normalize_url", lambda url: url)

    async def no_content(_url: str) -> None:
        return None

    monkeypatch.setattr(collector, "_extract_content", no_content)
    assert await collector._process_entry(source, feed, {"link": "https://example.com"}) is False

    async def content_fallback(_url: str) -> None:
        return None

    async def duplicate(*_args) -> bool:
        return True

    monkeypatch.setattr(collector, "_extract_content", content_fallback)
    monkeypatch.setattr(collector, "_is_duplicate", duplicate)
    entry = {"link": "https://example.com", "summary": "summary text", "title": "Headline"}
    assert await collector._process_entry(source, feed, entry) is False

    stored_payload: dict[str, object] = {}

    async def not_duplicate(*_args) -> bool:
        return False

    async def fake_store_item(**kwargs):
        stored_payload.update(kwargs)

    monkeypatch.setattr(collector, "_is_duplicate", not_duplicate)
    monkeypatch.setattr(collector, "_store_item", fake_store_item)
    assert await collector._process_entry(source, feed, entry) is False
    assert stored_payload["content"] == "summary text"


@pytest.mark.asyncio
async def test_process_entry_stores_extracted_article_content(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    source = SimpleNamespace(id=uuid4())
    feed = FeedConfig(name="Feed", url="https://example.com/rss", credibility=0.8)
    stored_payload: dict[str, object] = {}

    async def fake_extract_content(_url: str) -> str:
        return "full article"

    async def fake_is_duplicate(*_args) -> bool:
        return False

    async def fake_store_item(**kwargs):
        stored_payload.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(collector, "_extract_content", fake_extract_content)
    monkeypatch.setattr(collector, "_is_duplicate", fake_is_duplicate)
    monkeypatch.setattr(collector, "_store_item", fake_store_item)

    stored = await collector._process_entry(
        source,
        feed,
        {"link": "https://example.com/story", "title": "Headline"},
    )

    assert stored is True
    assert stored_payload["content"] == "full article"


@pytest.mark.asyncio
async def test_fetch_feed_preserves_bozo_parses(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    parsed = SimpleNamespace(bozo=True, bozo_exception=ValueError("bad"), entries=[])

    monkeypatch.setattr(collector, "_fetch_with_retries", AsyncMock(return_value="<rss></rss>"))
    monkeypatch.setattr("src.ingestion.rss_collector.feedparser.parse", lambda _raw: parsed)

    result = await collector._fetch_feed("https://example.com/rss")

    assert result is parsed


@pytest.mark.asyncio
async def test_fetch_feed_returns_clean_parse_without_bozo_warning(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    parsed = SimpleNamespace(bozo=False, entries=[{"title": "ok"}])

    monkeypatch.setattr(collector, "_fetch_with_retries", AsyncMock(return_value="<rss></rss>"))
    monkeypatch.setattr("src.ingestion.rss_collector.feedparser.parse", lambda _raw: parsed)

    result = await collector._fetch_feed("https://example.com/rss")

    assert result is parsed


@pytest.mark.asyncio
async def test_extract_content_uses_extractor_and_falls_back_on_fetch_error(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    monkeypatch.setattr(
        collector, "_fetch_with_retries", AsyncMock(return_value="<html>body</html>")
    )
    monkeypatch.setattr(
        "src.ingestion.rss_collector.ContentExtractor.extract_text",
        lambda html: f"text::{html}",
    )

    assert (
        await collector._extract_content("https://example.com/story") == "text::<html>body</html>"
    )

    monkeypatch.setattr(
        collector,
        "_fetch_with_retries",
        AsyncMock(side_effect=httpx.ReadTimeout("timeout")),
    )
    assert await collector._extract_content("https://example.com/story") is None


@pytest.mark.asyncio
async def test_fetch_with_retries_retries_http_status_with_retry_after(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    collector.max_retries = 1
    rate_wait = AsyncMock(return_value=None)
    sleep = AsyncMock(return_value=None)
    response_ok = MagicMock()
    response_ok.raise_for_status = MagicMock()
    response_ok.text = "<rss>ok</rss>"
    retry_response = MagicMock(status_code=429, headers={"Retry-After": "1.5"})
    request = httpx.Request("GET", "https://example.com/rss")
    mock_http_client.get = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("rate limit", request=request, response=retry_response),
            response_ok,
        ]
    )
    monkeypatch.setattr(collector.rate_limiter, "wait", rate_wait)
    monkeypatch.setattr("src.ingestion.rss_collector.asyncio.sleep", sleep)

    result = await collector._fetch_with_retries("https://example.com/rss", timeout_seconds=5)

    assert result == "<rss>ok</rss>"
    sleep.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_fetch_with_retries_raises_for_non_retryable_http_status(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    request = httpx.Request("GET", "https://example.com/rss")
    response = MagicMock(status_code=404, headers={})
    mock_http_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError("not found", request=request, response=response)
    )
    monkeypatch.setattr(collector.rate_limiter, "wait", AsyncMock(return_value=None))

    with pytest.raises(httpx.HTTPStatusError):
        await collector._fetch_with_retries("https://example.com/rss", timeout_seconds=5)


@pytest.mark.asyncio
async def test_fetch_with_retries_recovers_after_network_error(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    collector.max_retries = 1
    request = httpx.Request("GET", "https://example.com/rss")
    response_ok = MagicMock()
    response_ok.raise_for_status = MagicMock()
    response_ok.text = "<rss>ok</rss>"
    mock_http_client.get = AsyncMock(
        side_effect=[httpx.ConnectError("network", request=request), response_ok]
    )
    monkeypatch.setattr(collector.rate_limiter, "wait", AsyncMock(return_value=None))
    monkeypatch.setattr("src.ingestion.rss_collector.asyncio.sleep", AsyncMock(return_value=None))

    result = await collector._fetch_with_retries("https://example.com/rss", timeout_seconds=5)

    assert result == "<rss>ok</rss>"


@pytest.mark.asyncio
async def test_fetch_with_retries_raises_runtimeerror_when_retry_budget_is_negative(
    mock_db_session,
    mock_http_client,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    collector.max_retries = -1

    with pytest.raises(RuntimeError, match="unreachable retry loop state"):
        await collector._fetch_with_retries("https://example.com/rss", timeout_seconds=5)


@pytest.mark.asyncio
async def test_get_or_create_source_creates_and_updates_records(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(
        name="Feed",
        url="https://example.com/rss",
        credibility=0.9,
        categories=["conflict"],
        check_interval_minutes=15,
        max_items_per_fetch=10,
        language="en",
        source_tier="tier1",
        reporting_type="primary",
        enabled=False,
        extra={"region": "EMEA"},
    )
    refresh_mock = AsyncMock(return_value=1)
    monkeypatch.setattr("src.ingestion.rss_collector.refresh_events_for_source", refresh_mock)
    mock_db_session.scalar.return_value = None

    created = await collector._get_or_create_source(feed)

    assert created.name == "Feed"
    assert created.url == "https://example.com/rss"
    assert created.config["region"] == "EMEA"
    assert created.is_active is False
    refresh_mock.assert_not_awaited()

    existing = SimpleNamespace(
        id=uuid4(),
        name="Old",
        credibility_score=0.1,
        source_tier="regional",
        reporting_type="secondary",
        config={},
        is_active=True,
    )
    mock_db_session.scalar.return_value = existing

    updated = await collector._get_or_create_source(feed)

    assert updated is existing
    assert existing.name == "Feed"
    assert existing.credibility_score == 0.9
    assert existing.source_tier == "tier1"
    assert existing.reporting_type == "primary"
    assert existing.config["categories"] == ["conflict"]
    assert existing.is_active is False
    refresh_mock.assert_awaited_once_with(session=mock_db_session, source_id=existing.id)


@pytest.mark.asyncio
async def test_get_or_create_source_skips_provenance_refresh_when_metadata_is_unchanged(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(
        name="Feed",
        url="https://example.com/rss",
        credibility=0.9,
        categories=["conflict"],
        check_interval_minutes=15,
        max_items_per_fetch=10,
        language="en",
        source_tier="tier1",
        reporting_type="primary",
        enabled=False,
        extra={"region": "EMEA"},
    )
    refresh_mock = AsyncMock(return_value=0)
    monkeypatch.setattr("src.ingestion.rss_collector.refresh_events_for_source", refresh_mock)
    existing = SimpleNamespace(
        id=uuid4(),
        name="Feed",
        credibility_score=Decimal(str(feed.credibility)),
        source_tier="tier1",
        reporting_type="primary",
        config={},
        is_active=True,
    )
    mock_db_session.scalar.return_value = existing

    updated = await collector._get_or_create_source(feed)

    assert updated is existing
    refresh_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_source_refreshes_provenance_when_credibility_changes(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(
        name="Feed",
        url="https://example.com/rss",
        credibility=0.9,
        source_tier="tier1",
        reporting_type="primary",
    )
    refresh_mock = AsyncMock(return_value=1)
    monkeypatch.setattr("src.ingestion.rss_collector.refresh_events_for_source", refresh_mock)
    existing = SimpleNamespace(
        id=uuid4(),
        name="Feed",
        credibility_score=Decimal("0.1"),
        source_tier="tier1",
        reporting_type="primary",
        config={},
        is_active=True,
    )
    mock_db_session.scalar.return_value = existing

    await collector._get_or_create_source(feed)

    assert existing.credibility_score == pytest.approx(0.9)
    refresh_mock.assert_awaited_once_with(session=mock_db_session, source_id=existing.id)


@pytest.mark.asyncio
async def test_store_item_returns_none_on_insert_race(mock_db_session, mock_http_client) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    source = SimpleNamespace(id=uuid4())
    feed = FeedConfig(name="Feed", url="https://example.com/rss", credibility=0.8)

    @asynccontextmanager
    async def fake_begin_nested():
        yield

    mock_db_session.begin_nested = fake_begin_nested
    mock_db_session.flush.side_effect = IntegrityError("insert", {}, Exception("boom"))

    item = await collector._store_item(
        source=source,
        feed=feed,
        entry={},
        normalized_url="https://example.com/article",
        title=None,
        content="Body",
        content_hash="deadbeef",
    )

    assert item is None


def test_determine_collection_window_and_as_utc_normalize_naive_values(
    mock_db_session,
    mock_http_client,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    watermark = datetime(2026, 2, 15, 6, 0, tzinfo=UTC).replace(tzinfo=None)
    expected_start, actual_start = collector._determine_collection_window(
        source=SimpleNamespace(ingestion_window_end_at=watermark),
        now_utc=datetime(2026, 2, 16, 12, 0, tzinfo=UTC),
    )

    assert expected_start.tzinfo == UTC
    assert actual_start.tzinfo == UTC
    assert RSSCollector._window_coverage_metrics(
        expected_start=datetime(2026, 2, 16, 12, 5, tzinfo=UTC),
        actual_start=datetime(2026, 2, 16, 12, 10, tzinfo=UTC),
    ) == (300, 0)


@pytest.mark.asyncio
async def test_record_source_success_and_failure_update_state(
    mock_db_session,
    mock_http_client,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    source = SimpleNamespace(
        last_fetched_at=None,
        ingestion_window_end_at=None,
        error_count=2,
        last_error="old",
    )
    window_end = datetime(2026, 2, 16, 12, 0, tzinfo=UTC).replace(tzinfo=None)

    await collector._record_source_success(source, window_end=window_end)

    assert source.last_fetched_at is not None
    assert source.ingestion_window_end_at.tzinfo == UTC
    assert source.error_count == 0
    assert source.last_error is None

    await collector._record_source_failure(source, "x" * 1200)

    assert source.error_count == 1
    assert len(source.last_error) == 1000
    assert mock_db_session.flush.await_count == 2


@pytest.mark.asyncio
async def test_collect_feed_uses_published_timestamps_for_window_coverage(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = RSSCollector(session=mock_db_session, http_client=mock_http_client)
    feed = FeedConfig(name="Feed", url="https://example.com/rss", credibility=0.8)
    source = SimpleNamespace(error_count=0)
    watermark = datetime(2026, 2, 15, 12, 0, tzinfo=UTC)
    published_one = datetime(2026, 2, 15, 11, 55, tzinfo=UTC)
    published_two = datetime(2026, 2, 15, 12, 10, tzinfo=UTC)
    record_calls: list[datetime] = []

    async def fake_get_or_create_source(_feed: FeedConfig) -> SimpleNamespace:
        source.ingestion_window_end_at = watermark
        return source

    async def fake_fetch_feed(_url: str) -> SimpleNamespace:
        return SimpleNamespace(
            entries=[
                {"published_parsed": published_one.utctimetuple()},
                {"updated_parsed": published_two.utctimetuple()},
            ]
        )

    async def fake_process_entry(_source, _feed: FeedConfig, _entry) -> bool:
        return True

    async def fake_record_source_success(_source, *, window_end: datetime) -> None:
        record_calls.append(window_end)

    monkeypatch.setattr(collector, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(collector, "_fetch_feed", fake_fetch_feed)
    monkeypatch.setattr(collector, "_process_entry", fake_process_entry)
    monkeypatch.setattr(collector, "_record_source_success", fake_record_source_success)
    monkeypatch.setattr(settings, "INGESTION_WINDOW_OVERLAP_SECONDS", 120)

    result = await collector.collect_feed(feed)

    assert result.actual_start == published_one
    assert result.gap_seconds == 0
    assert result.overlap_seconds == 300
    assert record_calls == [published_two]


def test_parse_settings_and_feeds_cover_defaults_and_extras() -> None:
    parsed_settings = RSSCollector._parse_settings(
        {
            "request_timeout_seconds": "5",
            "user_agent": 123,
            "default_lookback_hours": "6",
        }
    )
    parsed_feeds = RSSCollector._parse_feeds(
        {"default_check_interval_minutes": 45, "default_max_items_per_fetch": 99},
        [
            {
                "name": " Feed ",
                "url": " https://example.com/rss ",
                "credibility": "0.8",
                "categories": ["a", 2],
                "language": " en ",
                "enabled": 0,
                "region": "EMEA",
            },
            {"name": "", "url": "https://skip"},
            "skip",
        ],
    )

    assert parsed_settings.request_timeout_seconds == 5
    assert parsed_settings.user_agent == "123"
    assert parsed_settings.default_lookback_hours == 6
    assert len(parsed_feeds) == 1
    assert parsed_feeds[0].name == "Feed"
    assert parsed_feeds[0].url == "https://example.com/rss"
    assert parsed_feeds[0].categories == ["a", "2"]
    assert parsed_feeds[0].check_interval_minutes == 45
    assert parsed_feeds[0].max_items_per_fetch == 99
    assert parsed_feeds[0].language == "en"
    assert parsed_feeds[0].enabled is False
    assert parsed_feeds[0].extra == {"region": "EMEA"}


def test_summary_entry_and_published_helpers_cover_fallbacks() -> None:
    assert RSSCollector._extract_summary({"summary": "summary"}) == "summary"
    assert RSSCollector._extract_summary({"content": [{"value": "body"}]}) == "body"
    assert RSSCollector._extract_summary({"content": [{"value": " "}, "skip"]}) is None
    assert RSSCollector._entry_link({"id": "https://example.com/id"}) == "https://example.com/id"
    assert RSSCollector._entry_title({"title": " Title "}) == "Title"
    published = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)
    assert (
        RSSCollector._parse_published_at({"updated_parsed": published.utctimetuple()}) == published
    )
    assert RSSCollector._parse_published_at({}) is None


def test_misc_helper_functions_cover_url_hash_retry_and_failure_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.ingestion.rss_collector.time.monotonic_ns", lambda: 1)
    request = httpx.Request("GET", "https://example.com")
    response_503 = httpx.Response(503, headers={}, request=request)
    response_404 = httpx.Response(404, headers={}, request=request)
    http_error = httpx.HTTPStatusError("bad", request=request, response=response_503)
    non_retryable_http_error = httpx.HTTPStatusError("bad", request=request, response=response_404)

    assert (
        RSSCollector._normalize_url("https://www.Example.com/path/?utm=1#frag")
        == "https://example.com/path"
    )
    assert len(RSSCollector._compute_hash("abc")) == 64
    assert RSSCollector._backoff_seconds(1) == 2.000000001
    assert RSSCollector._is_retryable_status(429) is True
    assert RSSCollector._is_retryable_status(404) is False
    assert RSSCollector._is_transient_failure(httpx.ReadTimeout("timeout")) is True
    assert RSSCollector._is_transient_failure(http_error) is True
    assert RSSCollector._is_transient_failure(non_retryable_http_error) is False
    assert RSSCollector._is_transient_failure(ValueError("boom")) is False
    assert RSSCollector._failure_reason(httpx.ReadTimeout("timeout")) == "timeout"
    assert RSSCollector._failure_reason(httpx.ConnectError("net", request=request)) == "network"
    assert RSSCollector._failure_reason(http_error) == "http_503"
    assert RSSCollector._failure_reason(ValueError("boom")) == "valueerror"
    assert RSSCollector._parse_retry_after(None) is None
    assert RSSCollector._parse_retry_after(" ") is None
    assert RSSCollector._parse_retry_after("bad") is None
    assert RSSCollector._parse_retry_after("-1") is None
    assert RSSCollector._parse_retry_after("2.5") == 2.5
    assert RSSCollector._safe_str(None) is None
    assert RSSCollector._safe_str("  ") is None
    assert RSSCollector._safe_str(" value ") == "value"
