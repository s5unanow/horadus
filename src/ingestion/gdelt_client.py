"""
GDELT DOC 2.0 ingestion client with filtering, pagination, and persistence.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.ingestion.rate_limiter import DomainRateLimiter
from src.processing.deduplication_service import DeduplicationService
from src.storage.models import ProcessingStatus, RawItem, Source, SourceType

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class GDELTQueryConfig:
    """GDELT query configuration loaded from YAML."""

    name: str
    query: str = ""
    credibility: float = 0.5
    themes: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    lookback_hours: int = 12
    max_records_per_page: int = 100
    max_pages: int = 3
    source_tier: str = "aggregator"
    reporting_type: str = "aggregator"
    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GDELTSettings:
    """Global GDELT settings from YAML."""

    request_timeout_seconds: int = 30
    user_agent: str = "GeopoliticalIntel/1.0 (GDELT Client)"
    default_lookback_hours: int = 12
    default_max_records_per_page: int = 100
    default_max_pages: int = 3


@dataclass(slots=True)
class GDELTCollectionResult:
    """Outcome metrics for one GDELT query collection run."""

    query_name: str
    pages_fetched: int = 0
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


class GDELTClient:
    """
    Collects and stores items from configured GDELT DOC 2.0 queries.
    """

    def __init__(
        self,
        session: AsyncSession,
        http_client: httpx.AsyncClient,
        config_path: str = "config/sources/gdelt_queries.yaml",
        api_url: str = "https://api.gdeltproject.org/api/v2/doc/doc",
        requests_per_second: float = 1.0,
    ) -> None:
        self.session = session
        self.http_client = http_client
        self.config_path = Path(config_path)
        self.api_url = api_url
        self.rate_limiter = DomainRateLimiter(requests_per_second=requests_per_second)

        self.settings = GDELTSettings()
        self._queries: list[GDELTQueryConfig] = []
        self._config_mtime: float | None = None

        self.total_timeout_seconds = settings.GDELT_COLLECTOR_TOTAL_TIMEOUT_SECONDS
        self.max_retries = 3
        self.dedup_window_days = 7
        self.deduplication_service = DeduplicationService(session=session)

    @property
    def queries(self) -> list[GDELTQueryConfig]:
        """Returns the currently loaded query configs."""
        return list(self._queries)

    async def load_config(self, force: bool = False) -> None:
        """Load or hot-reload GDELT query configuration from YAML."""
        if not self.config_path.exists():
            msg = f"GDELT config file not found: {self.config_path}"
            raise FileNotFoundError(msg)

        mtime = self.config_path.stat().st_mtime
        if not force and self._config_mtime is not None and mtime == self._config_mtime:
            return

        raw_config = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_config, dict):
            msg = "Invalid GDELT config format: expected mapping at top-level"
            raise ValueError(msg)

        settings_config = raw_config.get("settings", {})
        queries_config = raw_config.get("queries", [])

        if not isinstance(settings_config, dict):
            msg = "Invalid GDELT settings format"
            raise ValueError(msg)
        if not isinstance(queries_config, list):
            msg = "Invalid GDELT query list format"
            raise ValueError(msg)

        self.settings = self._parse_settings(settings_config)
        self._queries = self._parse_queries(settings_config, queries_config)
        self._config_mtime = mtime

        logger.info(
            "GDELT configuration loaded",
            config_path=str(self.config_path),
            queries=len(self._queries),
        )

    async def collect_all(self) -> list[GDELTCollectionResult]:
        """Collect from all enabled GDELT queries."""
        await self.load_config()
        results: list[GDELTCollectionResult] = []
        for query in self._queries:
            if not query.enabled:
                continue
            results.append(await self.collect_query(query))
        return results

    async def collect_query(self, query: GDELTQueryConfig) -> GDELTCollectionResult:
        """Collect from one configured GDELT query."""
        started = time.monotonic()
        result = GDELTCollectionResult(query_name=query.name)
        source = await self._get_or_create_source(query)

        now_utc = datetime.now(tz=UTC)
        expected_start, window_start = self._determine_collection_window(
            source=source,
            now_utc=now_utc,
            lookback_hours=query.lookback_hours,
        )
        gap_seconds, overlap_seconds = self._window_coverage_metrics(
            expected_start=expected_start,
            actual_start=window_start,
        )
        result.expected_start = expected_start
        result.actual_start = window_start
        result.gap_seconds = gap_seconds
        result.overlap_seconds = overlap_seconds
        window_end = now_utc

        logger.info(
            "GDELT collection window",
            query_name=query.name,
            expected_start=expected_start.isoformat(),
            actual_start=window_start.isoformat(),
            gap_seconds=gap_seconds,
            overlap_seconds=overlap_seconds,
        )

        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                while result.pages_fetched < query.max_pages:
                    articles = await self._fetch_articles(
                        query=query,
                        start_datetime=window_start,
                        end_datetime=window_end,
                        max_records=query.max_records_per_page,
                    )
                    if not articles:
                        break

                    result.pages_fetched += 1
                    result.items_fetched += len(articles)

                    oldest_published = self._oldest_published_at(articles)

                    for article in articles:
                        if not self._matches_filters(article, query):
                            result.items_skipped += 1
                            continue

                        published_at = self._parse_article_datetime(article)
                        stored_item = await self._store_article(
                            source=source,
                            article=article,
                            published_at=published_at,
                        )
                        if stored_item is None:
                            result.items_skipped += 1
                        else:
                            result.items_stored += 1

                    if len(articles) < query.max_records_per_page:
                        break
                    if oldest_published is None or oldest_published <= window_start:
                        break

                    next_window_end = oldest_published - timedelta(seconds=1)
                    if next_window_end >= window_end:
                        break
                    window_end = next_window_end
        except Exception as exc:
            failure_class = "transient" if self._is_transient_failure(exc) else "terminal"
            failure_reason = self._failure_reason(exc)
            if failure_class == "transient":
                result.transient_errors += 1
            else:
                result.terminal_errors += 1
            error_message = f"[{failure_class}] GDELT collection failed ({failure_reason}): {exc}"
            logger.warning(
                "GDELT query collection failed",
                query_name=query.name,
                query_expression=self._build_query_string(query),
                error=str(exc),
                failure_class=failure_class,
                failure_reason=failure_reason,
                timeout_budget_seconds=self.total_timeout_seconds,
                retry_attempts=max(1, self.max_retries + 1),
            )
            result.errors.append(error_message)
            await self._record_source_failure(source, error_message)
        else:
            await self._record_source_success(source, window_end=window_end)

        result.duration_seconds = round(time.monotonic() - started, 3)
        logger.info(
            "GDELT collection window coverage",
            query_name=query.name,
            expected_start=result.expected_start.isoformat() if result.expected_start else None,
            actual_start=result.actual_start.isoformat() if result.actual_start else None,
            gap_seconds=result.gap_seconds,
            overlap_seconds=result.overlap_seconds,
            pages_fetched=result.pages_fetched,
            items_fetched=result.items_fetched,
            items_stored=result.items_stored,
            items_skipped=result.items_skipped,
        )
        return result

    async def _fetch_articles(
        self,
        query: GDELTQueryConfig,
        start_datetime: datetime,
        end_datetime: datetime,
        max_records: int,
    ) -> list[dict[str, Any]]:
        params = {
            "query": self._build_query_string(query),
            "mode": "ArtList",
            "format": "json",
            "sort": "datedesc",
            "maxrecords": str(max_records),
            "startdatetime": self._format_gdelt_datetime(start_datetime),
            "enddatetime": self._format_gdelt_datetime(end_datetime),
        }
        payload = await self._request_json(params)

        raw_articles = payload.get("articles", [])
        if raw_articles is None:
            return []
        if not isinstance(raw_articles, list):
            msg = "GDELT response field 'articles' must be a list"
            raise ValueError(msg)

        return [article for article in raw_articles if isinstance(article, dict)]

    async def _request_json(self, params: dict[str, str]) -> dict[str, Any]:
        max_attempts = self.max_retries + 1

        for attempt in range(max_attempts):
            await self.rate_limiter.wait(self.api_url)
            try:
                response = await self.http_client.get(
                    self.api_url,
                    params=params,
                    timeout=self.settings.request_timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": self.settings.user_agent},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    msg = "GDELT response payload is not a JSON object"
                    raise ValueError(msg)
                return payload
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

    async def _get_or_create_source(self, query: GDELTQueryConfig) -> Source:
        existing_query = select(Source).where(
            Source.type == SourceType.GDELT,
            Source.name == query.name,
        )
        source = await self.session.scalar(existing_query)
        config_payload = {
            "query": query.query,
            "themes": query.themes,
            "actors": query.actors,
            "countries": query.countries,
            "languages": query.languages,
            "lookback_hours": query.lookback_hours,
            "max_records_per_page": query.max_records_per_page,
            "max_pages": query.max_pages,
            **query.extra,
        }

        if source is None:
            source = Source(
                type=SourceType.GDELT,
                name=query.name,
                url=self.api_url,
                credibility_score=query.credibility,
                source_tier=query.source_tier,
                reporting_type=query.reporting_type,
                config=config_payload,
                is_active=query.enabled,
            )
            self.session.add(source)
            await self.session.flush()
            return source

        source.url = self.api_url
        source.credibility_score = query.credibility
        source.source_tier = query.source_tier
        source.reporting_type = query.reporting_type
        source.config = config_payload
        source.is_active = query.enabled
        return source

    async def _store_article(
        self,
        source: Source,
        article: dict[str, Any],
        published_at: datetime | None,
    ) -> RawItem | None:
        raw_url = self._safe_str(article.get("url") or article.get("url_mobile"))
        normalized_url = self._normalize_url(raw_url) if raw_url is not None else None

        external_id = self._safe_str(article.get("id") or article.get("documentidentifier"))
        if external_id is None:
            external_id = normalized_url
        if external_id is None:
            return None

        title = self._safe_str(article.get("title"))
        raw_content = self._compose_raw_content(article, title, normalized_url)
        if raw_content is None:
            return None

        content_hash = self._compute_hash(raw_content)
        if await self._is_duplicate(normalized_url, external_id, content_hash):
            return None

        language = self._normalize_language(self._safe_str(article.get("language")))
        author = self._safe_str(article.get("domain") or article.get("sourcecommonname"))
        item = RawItem(
            source_id=source.id,
            external_id=external_id,
            url=normalized_url,
            title=title,
            author=author,
            published_at=published_at,
            raw_content=raw_content,
            content_hash=content_hash,
            language=language,
            processing_status=ProcessingStatus.PENDING,
        )

        try:
            async with self.session.begin_nested():
                self.session.add(item)
                await self.session.flush()
        except IntegrityError:
            logger.debug("Duplicate GDELT item skipped on insert race", external_id=external_id)
            return None
        return item

    async def _is_duplicate(
        self,
        normalized_url: str | None,
        external_id: str,
        content_hash: str,
    ) -> bool:
        result = await self.deduplication_service.find_duplicate(
            external_id=external_id,
            url=normalized_url,
            content_hash=content_hash,
            dedup_window_days=self.dedup_window_days,
        )
        return result.is_duplicate

    def _determine_collection_window(
        self,
        *,
        source: Source,
        now_utc: datetime,
        lookback_hours: int,
    ) -> tuple[datetime, datetime]:
        window_end_at = getattr(source, "ingestion_window_end_at", None)
        if window_end_at is None:
            expected_start = now_utc - timedelta(hours=max(1, lookback_hours))
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
    def _parse_settings(raw_settings: dict[str, Any]) -> GDELTSettings:
        return GDELTSettings(
            request_timeout_seconds=int(raw_settings.get("request_timeout_seconds", 30)),
            user_agent=str(raw_settings.get("user_agent", "GeopoliticalIntel/1.0 (GDELT Client)")),
            default_lookback_hours=int(raw_settings.get("default_lookback_hours", 12)),
            default_max_records_per_page=int(raw_settings.get("default_max_records_per_page", 100)),
            default_max_pages=int(raw_settings.get("default_max_pages", 3)),
        )

    @staticmethod
    def _parse_queries(
        raw_settings: dict[str, Any],
        raw_queries: list[Any],
    ) -> list[GDELTQueryConfig]:
        default_lookback_hours = int(raw_settings.get("default_lookback_hours", 12))
        default_max_records = int(raw_settings.get("default_max_records_per_page", 100))
        default_max_pages = int(raw_settings.get("default_max_pages", 3))

        parsed_queries: list[GDELTQueryConfig] = []
        for raw_query in raw_queries:
            if not isinstance(raw_query, dict):
                continue

            name = GDELTClient._safe_str(raw_query.get("name"))
            if name is None:
                continue

            query = GDELTClient._safe_str(raw_query.get("query")) or ""
            themes = GDELTClient._parse_str_list(raw_query.get("themes"))
            actors = GDELTClient._parse_str_list(raw_query.get("actors"))
            if not query and not themes and not actors:
                continue

            known_keys = {
                "name",
                "query",
                "credibility",
                "themes",
                "actors",
                "countries",
                "languages",
                "lookback_hours",
                "max_records_per_page",
                "max_pages",
                "source_tier",
                "reporting_type",
                "enabled",
            }
            extra = {key: value for key, value in raw_query.items() if key not in known_keys}

            parsed_queries.append(
                GDELTQueryConfig(
                    name=name,
                    query=query,
                    credibility=float(raw_query.get("credibility", 0.5)),
                    themes=themes,
                    actors=actors,
                    countries=GDELTClient._parse_str_list(raw_query.get("countries")),
                    languages=GDELTClient._parse_str_list(raw_query.get("languages")),
                    lookback_hours=int(raw_query.get("lookback_hours", default_lookback_hours)),
                    max_records_per_page=int(
                        raw_query.get("max_records_per_page", default_max_records)
                    ),
                    max_pages=int(raw_query.get("max_pages", default_max_pages)),
                    source_tier=str(raw_query.get("source_tier", "aggregator")),
                    reporting_type=str(raw_query.get("reporting_type", "aggregator")),
                    enabled=bool(raw_query.get("enabled", True)),
                    extra=extra,
                )
            )

        return parsed_queries

    @staticmethod
    def _parse_str_list(raw_value: Any) -> list[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, str):
            parts = raw_value.replace(";", ",").split(",")
            return [part.strip() for part in parts if part.strip()]
        if isinstance(raw_value, list):
            return [str(value).strip() for value in raw_value if str(value).strip()]
        return []

    @staticmethod
    def _build_query_string(query: GDELTQueryConfig) -> str:
        clauses: list[str] = []
        if query.query:
            clauses.append(f"({query.query})")

        if query.themes:
            theme_clause = " OR ".join(f"theme:{theme}" for theme in query.themes)
            clauses.append(f"({theme_clause})")
        if query.actors:
            actor_clause = " OR ".join(f'"{actor}"' for actor in query.actors)
            clauses.append(f"({actor_clause})")
        if query.countries:
            country_clause = " OR ".join(
                f"sourcecountry:{country.upper()}" for country in query.countries
            )
            clauses.append(f"({country_clause})")

        if not clauses:
            return "geopolitics"
        return " AND ".join(clauses)

    @staticmethod
    def _matches_filters(article: dict[str, Any], query: GDELTQueryConfig) -> bool:
        article_themes = {
            value.lower()
            for value in (
                GDELTClient._split_terms(article.get("themes"))
                + GDELTClient._split_terms(article.get("v2themes"))
                + GDELTClient._split_terms(article.get("theme"))
            )
        }
        if query.themes and not any(theme.lower() in article_themes for theme in query.themes):
            return False

        actor_terms = " ".join(
            GDELTClient._split_terms(article.get("persons"))
            + GDELTClient._split_terms(article.get("v2persons"))
            + GDELTClient._split_terms(article.get("organizations"))
            + GDELTClient._split_terms(article.get("v2organizations"))
            + GDELTClient._split_terms(article.get("actor1name"))
            + GDELTClient._split_terms(article.get("actor2name"))
            + GDELTClient._split_terms(article.get("title"))
        ).lower()
        if query.actors and not any(actor.lower() in actor_terms for actor in query.actors):
            return False

        if query.countries:
            article_country = GDELTClient._safe_str(
                article.get("sourcecountry") or article.get("source_country")
            )
            if article_country is None:
                return False
            allowed_countries = {country.upper() for country in query.countries}
            if article_country.upper() not in allowed_countries:
                return False

        if query.languages:
            raw_language = GDELTClient._safe_str(article.get("language"))
            normalized_language = GDELTClient._normalize_language(raw_language)
            if normalized_language is None:
                return False
            allowed_languages = {
                normalized
                for normalized in (
                    GDELTClient._normalize_language(language) for language in query.languages
                )
                if normalized is not None
            }
            if normalized_language not in allowed_languages:
                return False

        return True

    @staticmethod
    def _oldest_published_at(articles: list[dict[str, Any]]) -> datetime | None:
        parsed_dates = [
            published_at
            for published_at in (
                GDELTClient._parse_article_datetime(article) for article in articles
            )
            if published_at is not None
        ]
        if not parsed_dates:
            return None
        return min(parsed_dates)

    @staticmethod
    def _compose_raw_content(
        article: dict[str, Any],
        title: str | None,
        normalized_url: str | None,
    ) -> str | None:
        parts: list[str] = []
        if title:
            parts.append(title)

        for key in ("snippet", "summary", "description"):
            value = GDELTClient._safe_str(article.get(key))
            if value:
                parts.append(value)

        themes = GDELTClient._split_terms(article.get("themes")) + GDELTClient._split_terms(
            article.get("v2themes")
        )
        actors = (
            GDELTClient._split_terms(article.get("persons"))
            + GDELTClient._split_terms(article.get("v2persons"))
            + GDELTClient._split_terms(article.get("organizations"))
            + GDELTClient._split_terms(article.get("v2organizations"))
        )
        if themes:
            parts.append(f"Themes: {', '.join(themes)}")
        if actors:
            parts.append(f"Actors: {', '.join(actors)}")

        source_country = GDELTClient._safe_str(
            article.get("sourcecountry") or article.get("source_country")
        )
        if source_country:
            parts.append(f"Source country: {source_country}")

        domain = GDELTClient._safe_str(article.get("domain"))
        if domain:
            parts.append(f"Domain: {domain}")

        if normalized_url:
            parts.append(f"URL: {normalized_url}")

        if not parts:
            return None
        return "\n\n".join(parts)

    @staticmethod
    def _parse_article_datetime(article: dict[str, Any]) -> datetime | None:
        candidates = [
            article.get("seendate"),
            article.get("seenDate"),
            article.get("publishdate"),
            article.get("published"),
            article.get("date"),
        ]
        for candidate in candidates:
            parsed = GDELTClient._parse_datetime_value(candidate)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_datetime_value(raw_value: Any) -> datetime | None:
        if raw_value is None:
            return None

        if isinstance(raw_value, int | float):
            return datetime.fromtimestamp(float(raw_value), tz=UTC)

        if not isinstance(raw_value, str):
            return None

        stripped = raw_value.strip()
        if not stripped:
            return None

        compact_utc = (
            len(stripped) == 16
            and stripped[8] == "T"
            and stripped.endswith("Z")
            and stripped[:8].isdigit()
            and stripped[9:15].isdigit()
        )
        if compact_utc:
            try:
                return datetime(
                    int(stripped[0:4]),
                    int(stripped[4:6]),
                    int(stripped[6:8]),
                    int(stripped[9:11]),
                    int(stripped[11:13]),
                    int(stripped[13:15]),
                    tzinfo=UTC,
                )
            except ValueError:
                return None

        compact_without_tz = len(stripped) == 14 and stripped.isdigit()
        if compact_without_tz:
            try:
                return datetime(
                    int(stripped[0:4]),
                    int(stripped[4:6]),
                    int(stripped[6:8]),
                    int(stripped[8:10]),
                    int(stripped[10:12]),
                    int(stripped[12:14]),
                    tzinfo=UTC,
                )
            except ValueError:
                return None

        try:
            parsed_iso = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed_iso.tzinfo is None:
            return parsed_iso.replace(tzinfo=UTC)
        return parsed_iso.astimezone(UTC)

    @staticmethod
    def _format_gdelt_datetime(value: datetime) -> str:
        as_utc = value.astimezone(UTC)
        return as_utc.strftime("%Y%m%d%H%M%S")

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
    def _split_terms(raw_value: Any) -> list[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, str):
            normalized = raw_value.replace("|", ",").replace(";", ",")
            return [term.strip() for term in normalized.split(",") if term.strip()]
        if isinstance(raw_value, list):
            return [str(term).strip() for term in raw_value if str(term).strip()]
        return []

    @staticmethod
    def _normalize_language(raw_language: str | None) -> str | None:
        if raw_language is None:
            return None
        normalized = raw_language.strip().lower()
        if not normalized:
            return None

        aliases = {
            "english": "en",
            "russian": "ru",
            "ukrainian": "uk",
            "french": "fr",
            "spanish": "es",
            "german": "de",
            "arabic": "ar",
            "chinese": "zh",
        }
        if normalized in aliases:
            return aliases[normalized]
        return normalized

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

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
            return GDELTClient._is_retryable_status(exc.response.status_code)
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
    def _backoff_seconds(attempt: int) -> float:
        base = min(float(2**attempt), 30.0)
        jitter = (time.monotonic_ns() % 250_000_000) / 1_000_000_000
        return base + jitter

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
