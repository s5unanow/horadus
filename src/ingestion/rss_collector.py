"""
RSS feed ingestion with extraction, deduplication, and persistence.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import struct_time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx
import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.ingestion.content_extractor import ContentExtractor
from src.ingestion.rate_limiter import DomainRateLimiter
from src.processing.deduplication_service import DeduplicationService
from src.storage.models import ProcessingStatus, RawItem, Source, SourceType

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class FeedConfig:
    """RSS feed configuration loaded from YAML."""

    name: str
    url: str
    credibility: float
    categories: list[str] = field(default_factory=list)
    check_interval_minutes: int = 30
    max_items_per_fetch: int = 200
    language: str | None = None
    source_tier: str = "regional"
    reporting_type: str = "secondary"
    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CollectorSettings:
    """Global collector settings from YAML."""

    request_timeout_seconds: int = 30
    user_agent: str = "GeopoliticalIntel/1.0 (RSS Collector)"
    default_lookback_hours: int = 12


@dataclass(slots=True)
class CollectionResult:
    """Outcome metrics for one feed collection run."""

    feed_name: str
    items_fetched: int = 0
    items_stored: int = 0
    items_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    transient_errors: int = 0
    terminal_errors: int = 0
    expected_start: datetime | None = None
    actual_start: datetime | None = None
    gap_seconds: int = 0
    overlap_seconds: int = 0
    duration_seconds: float = 0.0


class RSSCollector:
    """
    Collects and stores items from configured RSS/Atom feeds.
    """

    def __init__(
        self,
        session: AsyncSession,
        http_client: httpx.AsyncClient,
        config_path: str = "config/sources/rss_feeds.yaml",
        requests_per_second: float = 1.0,
    ) -> None:
        self.session = session
        self.http_client = http_client
        self.config_path = Path(config_path)
        self.rate_limiter = DomainRateLimiter(requests_per_second=requests_per_second)

        self.settings = CollectorSettings()
        self._feeds: list[FeedConfig] = []
        self._config_mtime: float | None = None

        self.feed_total_timeout_seconds = settings.RSS_COLLECTOR_TOTAL_TIMEOUT_SECONDS
        self.article_timeout_seconds = 30
        self.max_retries = 3
        self.dedup_window_days = 7
        self.deduplication_service = DeduplicationService(session=session)

    @property
    def feeds(self) -> list[FeedConfig]:
        """Returns the currently loaded feed configs."""
        return list(self._feeds)

    async def load_config(self, force: bool = False) -> None:
        """
        Load or hot-reload feed configuration from YAML.
        """
        if not self.config_path.exists():
            msg = f"RSS config file not found: {self.config_path}"
            raise FileNotFoundError(msg)

        mtime = self.config_path.stat().st_mtime
        if not force and self._config_mtime is not None and mtime == self._config_mtime:
            return

        raw_config = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_config, dict):
            msg = "Invalid RSS config format: expected mapping at top-level"
            raise ValueError(msg)

        settings_config = raw_config.get("settings", {})
        feeds_config = raw_config.get("feeds", [])

        if not isinstance(settings_config, dict):
            msg = "Invalid RSS settings format"
            raise ValueError(msg)
        if not isinstance(feeds_config, list):
            msg = "Invalid RSS feed list format"
            raise ValueError(msg)

        self.settings = self._parse_settings(settings_config)
        self._feeds = self._parse_feeds(settings_config, feeds_config)
        self._config_mtime = mtime

        logger.info(
            "RSS configuration loaded",
            config_path=str(self.config_path),
            feeds=len(self._feeds),
        )

    async def collect_all(self) -> list[CollectionResult]:
        """
        Collect from all enabled feeds.
        """
        await self.load_config()
        results: list[CollectionResult] = []
        for feed in self._feeds:
            if not feed.enabled:
                continue
            results.append(await self.collect_feed(feed))
        return results

    async def collect_feed(self, feed: FeedConfig) -> CollectionResult:
        """
        Collect from a single feed and return collection metrics.
        """
        started = time.monotonic()
        result = CollectionResult(feed_name=feed.name)

        source = await self._get_or_create_source(feed)
        now_utc = datetime.now(tz=UTC)
        expected_start, window_start = self._determine_collection_window(
            source=source,
            now_utc=now_utc,
        )
        result.expected_start = expected_start
        result.actual_start = window_start

        logger.info(
            "RSS collection window",
            feed=feed.name,
            expected_start=expected_start.isoformat(),
            actual_start=window_start.isoformat(),
        )

        published_timestamps: list[datetime] = []

        try:
            async with asyncio.timeout(self.feed_total_timeout_seconds):
                parsed_feed = await self._fetch_feed(feed.url)
                entries = list(getattr(parsed_feed, "entries", []))
                result.items_fetched = min(len(entries), feed.max_items_per_fetch)

                for entry in entries[: feed.max_items_per_fetch]:
                    entry_data = dict(entry) if hasattr(entry, "items") else {}
                    published_at = self._parse_published_at(entry_data)
                    if published_at is not None:
                        published_timestamps.append(published_at)
                    try:
                        was_stored = await self._process_entry(source, feed, entry)
                    except Exception as exc:
                        logger.warning(
                            "RSS entry processing failed",
                            feed=feed.name,
                            source_url=feed.url,
                            error=str(exc),
                        )
                        result.errors.append(str(exc))
                        continue

                    if was_stored:
                        result.items_stored += 1
                    else:
                        result.items_skipped += 1
        except Exception as exc:
            failure_class = "transient" if self._is_transient_failure(exc) else "terminal"
            failure_reason = self._failure_reason(exc)
            if failure_class == "transient":
                result.transient_errors += 1
            else:
                result.terminal_errors += 1
            error_message = f"[{failure_class}] Feed collection failed ({failure_reason}): {exc}"
            logger.warning(
                "RSS feed collection failed",
                feed=feed.name,
                source_url=feed.url,
                error=str(exc),
                failure_class=failure_class,
                failure_reason=failure_reason,
                timeout_budget_seconds=self.feed_total_timeout_seconds,
                retry_attempts=max(1, self.max_retries + 1),
            )
            result.errors.append(error_message)
            await self._record_source_failure(source, error_message)
        else:
            if published_timestamps:
                result.actual_start = min(published_timestamps)
                window_end = max(published_timestamps)
            else:
                result.actual_start = window_start
                window_end = now_utc

            gap_seconds, overlap_seconds = self._window_coverage_metrics(
                expected_start=expected_start,
                actual_start=result.actual_start,
            )
            result.gap_seconds = gap_seconds
            result.overlap_seconds = overlap_seconds
            await self._record_source_success(source, window_end=window_end)

        result.duration_seconds = round(time.monotonic() - started, 3)
        logger.info(
            "RSS collection window coverage",
            feed=feed.name,
            expected_start=result.expected_start.isoformat() if result.expected_start else None,
            actual_start=result.actual_start.isoformat() if result.actual_start else None,
            gap_seconds=result.gap_seconds,
            overlap_seconds=result.overlap_seconds,
            items_fetched=result.items_fetched,
            items_stored=result.items_stored,
            items_skipped=result.items_skipped,
        )
        return result

    async def _process_entry(self, source: Source, feed: FeedConfig, entry: Any) -> bool:
        entry_data = dict(entry) if hasattr(entry, "items") else {}
        raw_link = self._entry_link(entry_data)
        if raw_link is None:
            return False

        normalized_url = self._normalize_url(raw_link)
        if normalized_url is None:
            return False

        title = self._entry_title(entry_data)
        summary = self._extract_summary(entry_data) or title

        content = await self._extract_content(normalized_url)
        if content is None:
            content = summary
        if content is None:
            return False

        content_hash = self._compute_hash(content)
        if await self._is_duplicate(normalized_url, content_hash):
            return False

        stored_item = await self._store_item(
            source=source,
            feed=feed,
            entry=entry_data,
            normalized_url=normalized_url,
            title=title,
            content=content,
            content_hash=content_hash,
        )
        return stored_item is not None

    async def _fetch_feed(self, url: str) -> feedparser.FeedParserDict:
        raw_feed = await self._fetch_with_retries(
            url=url,
            timeout_seconds=self.settings.request_timeout_seconds,
        )
        parsed = feedparser.parse(raw_feed)

        if getattr(parsed, "bozo", False):
            logger.warning(
                "Malformed RSS/Atom feed parsed with warnings",
                url=url,
                bozo_exception=str(getattr(parsed, "bozo_exception", "")),
            )

        return parsed

    async def _extract_content(self, url: str) -> str | None:
        try:
            html = await self._fetch_with_retries(
                url=url,
                timeout_seconds=self.article_timeout_seconds,
            )
        except Exception as exc:
            logger.debug("Article fetch failed; fallback to summary", url=url, error=str(exc))
            return None
        return ContentExtractor.extract_text(html)

    async def _fetch_with_retries(self, url: str, timeout_seconds: int) -> str:
        max_attempts = self.max_retries + 1

        for attempt in range(max_attempts):
            await self.rate_limiter.wait(url)
            try:
                response = await self.http_client.get(
                    url,
                    timeout=timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": self.settings.user_agent},
                )
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                should_retry = self._is_retryable_status(status_code)
                if not should_retry or attempt + 1 >= max_attempts:
                    raise
                retry_after = self._parse_retry_after(exc.response.headers.get("Retry-After"))
                delay = retry_after if retry_after is not None else self._backoff_seconds(attempt)
                await asyncio.sleep(delay)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt + 1 >= max_attempts:
                    raise
                await asyncio.sleep(self._backoff_seconds(attempt))

        msg = "unreachable retry loop state"
        raise RuntimeError(msg)

    async def _get_or_create_source(self, feed: FeedConfig) -> Source:
        query = select(Source).where(
            Source.type == SourceType.RSS,
            Source.url == feed.url,
        )
        source = await self.session.scalar(query)
        if source is None:
            source = Source(
                type=SourceType.RSS,
                name=feed.name,
                url=feed.url,
                credibility_score=feed.credibility,
                source_tier=feed.source_tier,
                reporting_type=feed.reporting_type,
                config={
                    "categories": feed.categories,
                    "check_interval_minutes": feed.check_interval_minutes,
                    "max_items_per_fetch": feed.max_items_per_fetch,
                    "language": feed.language,
                    **feed.extra,
                },
                is_active=feed.enabled,
            )
            self.session.add(source)
            await self.session.flush()
            return source

        source.name = feed.name
        source.credibility_score = feed.credibility
        source.source_tier = feed.source_tier
        source.reporting_type = feed.reporting_type
        source.config = {
            "categories": feed.categories,
            "check_interval_minutes": feed.check_interval_minutes,
            "max_items_per_fetch": feed.max_items_per_fetch,
            "language": feed.language,
            **feed.extra,
        }
        source.is_active = feed.enabled
        return source

    async def _is_duplicate(self, normalized_url: str, content_hash: str) -> bool:
        result = await self.deduplication_service.find_duplicate(
            external_id=normalized_url,
            url=normalized_url,
            content_hash=content_hash,
            dedup_window_days=self.dedup_window_days,
        )
        return result.is_duplicate

    async def _store_item(
        self,
        source: Source,
        feed: FeedConfig,
        entry: dict[str, Any],
        normalized_url: str,
        title: str | None,
        content: str,
        content_hash: str,
    ) -> RawItem | None:
        language = self._safe_str(entry.get("language")) or feed.language
        published_at = self._parse_published_at(entry)
        author = self._safe_str(entry.get("author"))

        item = RawItem(
            source_id=source.id,
            external_id=normalized_url,
            url=normalized_url,
            title=title,
            author=author,
            published_at=published_at,
            raw_content=content,
            content_hash=content_hash,
            language=language,
            processing_status=ProcessingStatus.PENDING,
        )

        try:
            async with self.session.begin_nested():
                self.session.add(item)
                await self.session.flush()
        except IntegrityError:
            logger.debug("Duplicate item skipped on insert race", url=normalized_url)
            return None
        return item

    def _determine_collection_window(
        self,
        *,
        source: Source,
        now_utc: datetime,
    ) -> tuple[datetime, datetime]:
        window_end_at = getattr(source, "ingestion_window_end_at", None)
        if window_end_at is None:
            expected_start = now_utc - timedelta(hours=max(1, self.settings.default_lookback_hours))
            return (expected_start, expected_start)

        expected_start = self._as_utc(window_end_at)
        overlap_seconds = max(0, settings.INGESTION_WINDOW_OVERLAP_SECONDS)
        actual_start = expected_start - timedelta(seconds=overlap_seconds)
        return (expected_start, actual_start)

    @staticmethod
    def _window_coverage_metrics(
        *,
        expected_start: datetime,
        actual_start: datetime,
    ) -> tuple[int, int]:
        gap_seconds = max(0, int((actual_start - expected_start).total_seconds()))
        overlap_seconds = max(0, int((expected_start - actual_start).total_seconds()))
        return (gap_seconds, overlap_seconds)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    async def _record_source_success(self, source: Source, *, window_end: datetime) -> None:
        source.last_fetched_at = datetime.now(tz=UTC)
        source.ingestion_window_end_at = self._as_utc(window_end)
        source.error_count = 0
        source.last_error = None
        await self.session.flush()

    async def _record_source_failure(self, source: Source, error: str) -> None:
        source.error_count = source.error_count + 1
        source.last_error = error[:1000]
        await self.session.flush()

    @staticmethod
    def _parse_settings(raw_settings: dict[str, Any]) -> CollectorSettings:
        timeout_value = raw_settings.get("request_timeout_seconds", 30)
        user_agent = raw_settings.get("user_agent", "GeopoliticalIntel/1.0 (RSS Collector)")
        return CollectorSettings(
            request_timeout_seconds=int(timeout_value),
            user_agent=str(user_agent),
            default_lookback_hours=int(raw_settings.get("default_lookback_hours", 12)),
        )

    @staticmethod
    def _parse_feeds(
        raw_settings: dict[str, Any],
        raw_feeds: list[Any],
    ) -> list[FeedConfig]:
        default_interval = int(raw_settings.get("default_check_interval_minutes", 30))
        default_max_items = int(raw_settings.get("default_max_items_per_fetch", 200))

        parsed_feeds: list[FeedConfig] = []
        for raw_feed in raw_feeds:
            if not isinstance(raw_feed, dict):
                continue
            name = str(raw_feed.get("name", "")).strip()
            url = str(raw_feed.get("url", "")).strip()
            if not name or not url:
                continue

            categories_raw = raw_feed.get("categories", [])
            categories = (
                [str(category) for category in categories_raw]
                if isinstance(categories_raw, list)
                else []
            )
            known_keys = {
                "name",
                "url",
                "credibility",
                "categories",
                "check_interval_minutes",
                "max_items_per_fetch",
                "language",
                "source_tier",
                "reporting_type",
                "enabled",
            }
            extra = {key: value for key, value in raw_feed.items() if key not in known_keys}

            parsed_feeds.append(
                FeedConfig(
                    name=name,
                    url=url,
                    credibility=float(raw_feed.get("credibility", 0.5)),
                    categories=categories,
                    check_interval_minutes=int(
                        raw_feed.get("check_interval_minutes", default_interval)
                    ),
                    max_items_per_fetch=int(raw_feed.get("max_items_per_fetch", default_max_items)),
                    language=RSSCollector._safe_str(raw_feed.get("language")),
                    source_tier=str(raw_feed.get("source_tier", "regional")),
                    reporting_type=str(raw_feed.get("reporting_type", "secondary")),
                    enabled=bool(raw_feed.get("enabled", True)),
                    extra=extra,
                )
            )
        return parsed_feeds

    @staticmethod
    def _extract_summary(entry: dict[str, Any]) -> str | None:
        summary = RSSCollector._safe_str(entry.get("summary") or entry.get("description"))
        if summary:
            return summary

        content_blocks = entry.get("content")
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if isinstance(block, dict):
                    value = RSSCollector._safe_str(block.get("value"))
                    if value:
                        return value
        return None

    @staticmethod
    def _entry_link(entry: dict[str, Any]) -> str | None:
        return RSSCollector._safe_str(entry.get("link") or entry.get("id"))

    @staticmethod
    def _entry_title(entry: dict[str, Any]) -> str | None:
        return RSSCollector._safe_str(entry.get("title"))

    @staticmethod
    def _parse_published_at(entry: dict[str, Any]) -> datetime | None:
        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if isinstance(published_parsed, struct_time):
            unix_time = calendar.timegm(published_parsed)
            return datetime.fromtimestamp(unix_time, tz=UTC)
        return None

    @staticmethod
    def _normalize_url(url: str) -> str | None:
        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return None

        if not parsed.scheme or not parsed.netloc:
            return None

        hostname = parsed.hostname.lower() if parsed.hostname else ""
        if hostname.startswith("www."):
            hostname = hostname[4:]

        netloc = hostname
        if parsed.port is not None:
            is_default_port = (parsed.scheme == "http" and parsed.port == 80) or (
                parsed.scheme == "https" and parsed.port == 443
            )
            if not is_default_port:
                netloc = f"{hostname}:{parsed.port}"

        path = parsed.path.rstrip("/") or "/"
        return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        base = min(float(2**attempt), 30.0)
        jitter = (time.monotonic_ns() % 250_000_000) / 1_000_000_000
        return base + jitter

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    @staticmethod
    def _is_transient_failure(exc: BaseException) -> bool:
        if isinstance(
            exc, httpx.TimeoutException | httpx.NetworkError | TimeoutError | asyncio.TimeoutError
        ):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return RSSCollector._is_retryable_status(exc.response.status_code)
        return False

    @staticmethod
    def _failure_reason(exc: BaseException) -> str:
        if isinstance(exc, httpx.TimeoutException | TimeoutError | asyncio.TimeoutError):
            return "timeout"
        if isinstance(exc, httpx.NetworkError):
            return "network"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"http_{exc.response.status_code}"
        return type(exc).__name__.lower()

    @staticmethod
    def _parse_retry_after(raw_retry_after: str | None) -> float | None:
        if raw_retry_after is None:
            return None
        retry_after = raw_retry_after.strip()
        if not retry_after:
            return None
        try:
            parsed = float(retry_after)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        if value is None:
            return None
        as_str = str(value).strip()
        return as_str or None
