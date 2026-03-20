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

from src.ingestion.gdelt_client import GDELTClient, GDELTQueryConfig
from src.storage.models import Source, SourceType

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_load_config_covers_missing_invalid_and_hot_reload_skip(
    tmp_path: Path,
    mock_db_session,
    mock_http_client,
) -> None:
    client = GDELTClient(
        session=mock_db_session,
        http_client=mock_http_client,
        config_path=str(tmp_path / "missing.yaml"),
    )
    with pytest.raises(FileNotFoundError, match="GDELT config file not found"):
        await client.load_config()

    invalid_root = tmp_path / "invalid_root.yaml"
    invalid_root.write_text("- nope\n", encoding="utf-8")
    client.config_path = invalid_root
    with pytest.raises(ValueError, match="expected mapping"):
        await client.load_config(force=True)

    invalid_settings = tmp_path / "invalid_settings.yaml"
    invalid_settings.write_text("settings: []\nqueries: []\n", encoding="utf-8")
    client.config_path = invalid_settings
    with pytest.raises(ValueError, match="Invalid GDELT settings format"):
        await client.load_config(force=True)

    invalid_queries = tmp_path / "invalid_queries.yaml"
    invalid_queries.write_text("settings: {}\nqueries: {}\n", encoding="utf-8")
    client.config_path = invalid_queries
    with pytest.raises(ValueError, match="Invalid GDELT query list format"):
        await client.load_config(force=True)

    valid = tmp_path / "valid.yaml"
    valid.write_text("settings: {}\nqueries: [{name: Q, query: ukraine}]\n", encoding="utf-8")
    client.config_path = valid
    await client.load_config(force=True)
    loaded_queries = client.queries
    await client.load_config(force=False)
    assert client.queries[0].name == loaded_queries[0].name


@pytest.mark.asyncio
async def test_collect_all_skips_disabled_queries(mock_db_session, mock_http_client) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    client.load_config = AsyncMock(return_value=None)
    client._queries = [
        GDELTQueryConfig(name="enabled", query="x", enabled=True),
        GDELTQueryConfig(name="disabled", query="y", enabled=False),
    ]
    client.collect_query = AsyncMock(return_value=SimpleNamespace(query_name="enabled"))

    result = await client.collect_all()

    assert [row.query_name for row in result] == ["enabled"]
    client.collect_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_articles_and_request_json_cover_error_paths(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    monkeypatch.setattr(client, "_request_json", AsyncMock(return_value={"articles": None}))
    query = GDELTQueryConfig(name="q", query="ukraine")
    assert (
        await client._fetch_articles(
            query=query,
            start_datetime=datetime.now(tz=UTC),
            end_datetime=datetime.now(tz=UTC),
            max_records=10,
        )
        == []
    )

    monkeypatch.setattr(client, "_request_json", AsyncMock(return_value={"articles": "bad"}))
    with pytest.raises(ValueError, match="'articles' must be a list"):
        await client._fetch_articles(
            query=query,
            start_datetime=datetime.now(tz=UTC),
            end_datetime=datetime.now(tz=UTC),
            max_records=10,
        )

    client_request = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=[])
    mock_http_client.get = AsyncMock(return_value=response)
    monkeypatch.setattr(client_request.rate_limiter, "wait", AsyncMock(return_value=None))
    with pytest.raises(ValueError, match="not a JSON object"):
        await client_request._request_json({"query": "x"})

    status_response = MagicMock(status_code=429, headers={"Retry-After": "1.5"})
    status_exc = httpx.HTTPStatusError("rate limit", request=MagicMock(), response=status_response)
    ok_response = MagicMock()
    ok_response.raise_for_status = MagicMock()
    ok_response.json = MagicMock(return_value={"articles": []})
    mock_http_client.get = AsyncMock(side_effect=[status_exc, ok_response])
    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr("src.ingestion.gdelt_client.asyncio.sleep", sleep_mock)

    payload = await client_request._request_json({"query": "x"})
    assert payload == {"articles": []}
    sleep_mock.assert_awaited_once_with(1.5)

    monkeypatch.setattr(
        client,
        "_request_json",
        AsyncMock(return_value={"articles": [None, {"url": "https://example.com"}]}),
    )
    raw_articles = await client._fetch_articles(
        query=query,
        start_datetime=datetime.now(tz=UTC),
        end_datetime=datetime.now(tz=UTC),
        max_records=10,
    )
    assert raw_articles == [{"url": "https://example.com"}]

    non_retry_response = MagicMock(status_code=400, headers={})
    non_retry_exc = httpx.HTTPStatusError(
        "bad request",
        request=MagicMock(),
        response=non_retry_response,
    )
    mock_http_client.get = AsyncMock(side_effect=non_retry_exc)
    with pytest.raises(httpx.HTTPStatusError):
        await client_request._request_json({"query": "x"})

    client_request.max_retries = -1
    with pytest.raises(RuntimeError, match="unreachable retry loop state"):
        await client_request._request_json({"query": "x"})


@pytest.mark.asyncio
async def test_get_or_create_source_and_store_article_cover_update_and_early_returns(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    query = GDELTQueryConfig(
        name="Query",
        query="ukraine",
        enabled=False,
        source_tier="official",
        reporting_type="firsthand",
    )
    refresh_mock = AsyncMock(return_value=1)
    monkeypatch.setattr("src.ingestion.gdelt_client.refresh_events_for_source", refresh_mock)

    mock_db_session.scalar = AsyncMock(return_value=None)
    created = await client._get_or_create_source(query)
    assert isinstance(created, Source)
    assert created.type == SourceType.GDELT
    assert created.is_active is False
    refresh_mock.assert_not_awaited()

    existing = SimpleNamespace(
        id=uuid4(),
        name="Old Query",
        url="old",
        credibility_score=0.1,
        source_tier="aggregator",
        reporting_type="aggregator",
        config={},
        is_active=True,
    )
    mock_db_session.scalar = AsyncMock(return_value=existing)
    updated = await client._get_or_create_source(query)
    assert updated is existing
    assert existing.url == client.api_url
    assert existing.source_tier == "official"
    refresh_mock.assert_awaited_once_with(session=mock_db_session, source_id=existing.id)

    source = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(client, "_is_duplicate", AsyncMock(return_value=False))
    assert await client._store_article(source=source, article={}, published_at=None) is None
    assert (
        await client._store_article(
            source=source,
            article={"id": "article-1"},
            published_at=None,
        )
        is None
    )
    monkeypatch.setattr(client, "_is_duplicate", AsyncMock(return_value=True))
    assert (
        await client._store_article(
            source=source,
            article={"url": "https://example.com/2", "title": "Title"},
            published_at=None,
        )
        is None
    )

    @asynccontextmanager
    async def raising_nested():
        yield
        raise IntegrityError("insert", {}, Exception("duplicate"))

    mock_db_session.begin_nested = raising_nested
    monkeypatch.setattr(client, "_is_duplicate", AsyncMock(return_value=False))
    stored = await client._store_article(
        source=source,
        article={"url": "https://example.com/3", "title": "Title"},
        published_at=datetime.now(tz=UTC),
    )
    assert stored is None


@pytest.mark.asyncio
async def test_get_or_create_source_skips_provenance_refresh_when_metadata_is_unchanged(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    query = GDELTQueryConfig(
        name="Query",
        query="ukraine",
        enabled=False,
        source_tier="official",
        reporting_type="firsthand",
    )
    refresh_mock = AsyncMock(return_value=0)
    monkeypatch.setattr("src.ingestion.gdelt_client.refresh_events_for_source", refresh_mock)
    existing = SimpleNamespace(
        id=uuid4(),
        name="Query",
        url=client.api_url,
        credibility_score=Decimal(str(query.credibility)),
        source_tier="official",
        reporting_type="firsthand",
        config={},
        is_active=True,
    )
    mock_db_session.scalar = AsyncMock(return_value=existing)

    updated = await client._get_or_create_source(query)

    assert updated is existing
    refresh_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_source_refreshes_provenance_when_credibility_changes(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    query = GDELTQueryConfig(
        name="Query",
        query="ukraine",
        credibility=0.9,
        source_tier="official",
        reporting_type="firsthand",
    )
    refresh_mock = AsyncMock(return_value=1)
    monkeypatch.setattr("src.ingestion.gdelt_client.refresh_events_for_source", refresh_mock)
    existing = SimpleNamespace(
        id=uuid4(),
        name="Query",
        url=client.api_url,
        credibility_score=Decimal("0.1"),
        source_tier="official",
        reporting_type="firsthand",
        config={},
        is_active=True,
    )
    mock_db_session.scalar = AsyncMock(return_value=existing)

    await client._get_or_create_source(query)

    assert existing.credibility_score == pytest.approx(0.9)
    refresh_mock.assert_awaited_once_with(session=mock_db_session, source_id=existing.id)


def test_gdelt_helper_functions_cover_parsing_and_filters() -> None:
    assert GDELTClient._parse_settings({}).default_max_pages == 3
    parsed = GDELTClient._parse_queries(
        {"default_lookback_hours": 6, "default_max_records_per_page": 10, "default_max_pages": 2},
        [
            "bad",
            {"name": "", "query": "x"},
            {"name": "missing", "query": "", "themes": [], "actors": []},
            {"name": "ok", "query": "ukraine", "languages": "english;ukrainian", "custom": 1},
        ],
    )
    assert len(parsed) == 1
    assert parsed[0].lookback_hours == 6
    assert parsed[0].languages == ["english", "ukrainian"]
    assert parsed[0].extra == {"custom": 1}

    assert GDELTClient._parse_str_list(None) == []
    assert GDELTClient._parse_str_list("a;b, c") == ["a", "b", "c"]
    assert GDELTClient._parse_str_list([1, " ", "x"]) == ["1", "x"]
    assert GDELTClient._parse_str_list(1) == []
    assert GDELTClient._build_query_string(GDELTQueryConfig(name="q")) == "geopolitics"

    article = {"themes": "POLITICS", "persons": "OSCE", "sourcecountry": "UA", "language": "French"}
    assert not GDELTClient._matches_filters(
        article, GDELTQueryConfig(name="q", themes=["military"])
    )
    assert not GDELTClient._matches_filters(article, GDELTQueryConfig(name="q", actors=["NATO"]))
    assert not GDELTClient._matches_filters(article, GDELTQueryConfig(name="q", countries=["PL"]))
    assert not GDELTClient._matches_filters(article, GDELTQueryConfig(name="q", languages=["en"]))
    assert not GDELTClient._matches_filters(
        {"sourcecountry": None, "language": None},
        GDELTQueryConfig(name="q", countries=["UA"], languages=["en"]),
    )

    assert GDELTClient._oldest_published_at([{"seendate": "bad"}]) is None
    assert GDELTClient._compose_raw_content({}, None, None) is None
    composed = GDELTClient._compose_raw_content(
        {
            "snippet": "Snippet",
            "themes": "MILITARY",
            "persons": "NATO",
            "sourcecountry": "UA",
            "domain": "example.com",
        },
        "Title",
        "https://example.com/a",
    )
    assert composed is not None
    assert "Themes: MILITARY" in composed
    assert "Actors: NATO" in composed

    assert GDELTClient._parse_article_datetime({"date": "20260206103000"}) == datetime(
        2026,
        2,
        6,
        10,
        30,
        tzinfo=UTC,
    )
    assert GDELTClient._parse_datetime_value(None) is None
    assert GDELTClient._parse_datetime_value(1738837800) is not None
    assert GDELTClient._parse_datetime_value(object()) is None
    assert GDELTClient._parse_datetime_value(" ") is None
    assert GDELTClient._parse_datetime_value("20260206T103000Z") == datetime(
        2026,
        2,
        6,
        10,
        30,
        tzinfo=UTC,
    )
    assert GDELTClient._parse_datetime_value("20260206103000") == datetime(
        2026,
        2,
        6,
        10,
        30,
        tzinfo=UTC,
    )
    assert GDELTClient._parse_datetime_value("2026-02-06T10:30:00Z") == datetime(
        2026,
        2,
        6,
        10,
        30,
        tzinfo=UTC,
    )
    assert GDELTClient._parse_datetime_value("20260231T103000Z") is None
    assert GDELTClient._parse_datetime_value("20260231103000") is None
    assert GDELTClient._parse_datetime_value("2026-02-06T10:30:00") == datetime(
        2026,
        2,
        6,
        10,
        30,
        tzinfo=UTC,
    )
    assert GDELTClient._parse_datetime_value("bad") is None
    assert (
        GDELTClient._format_gdelt_datetime(datetime(2026, 2, 6, 10, 30, tzinfo=UTC))
        == "20260206103000"
    )
    assert GDELTClient._split_terms([" a ", "", 1]) == ["a", "1"]
    assert GDELTClient._split_terms(1) == []
    assert GDELTClient._normalize_language(None) is None
    assert GDELTClient._normalize_language(" English ") == "en"
    assert GDELTClient._normalize_language("pl") == "pl"
    assert GDELTClient._normalize_language("   ") is None
    assert len(GDELTClient._compute_hash("content")) == 64
    assert GDELTClient._is_retryable_status(429) is True
    assert GDELTClient._is_retryable_status(503) is True
    assert GDELTClient._is_retryable_status(400) is False
    assert GDELTClient._failure_reason(TimeoutError()) == "timeout"
    assert GDELTClient._failure_reason(httpx.ConnectError("x")) == "network"
    assert (
        GDELTClient._failure_reason(
            httpx.HTTPStatusError(
                "bad", request=MagicMock(), response=SimpleNamespace(status_code=502)
            )
        )
        == "http_502"
    )
    assert GDELTClient._failure_reason(ValueError("bad")) == "valueerror"
    assert GDELTClient._parse_retry_after(None) is None
    assert GDELTClient._parse_retry_after("") is None
    assert GDELTClient._parse_retry_after("bad") is None
    assert GDELTClient._parse_retry_after("-1") is None
    assert GDELTClient._parse_retry_after("2.5") == pytest.approx(2.5)
    assert GDELTClient._safe_str(None) is None
    assert GDELTClient._safe_str("  value ") == "value"


def test_gdelt_window_and_failure_helpers_cover_remaining_paths(
    mock_db_session,
    mock_http_client,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    now = datetime(2026, 2, 6, 10, 30, tzinfo=UTC)
    expected, _actual = client._determine_collection_window(
        source=SimpleNamespace(
            ingestion_window_end_at=datetime(2026, 2, 6, 8, 0, tzinfo=UTC).replace(tzinfo=None)
        ),
        now_utc=now,
        lookback_hours=0,
    )
    assert expected == datetime(2026, 2, 6, 8, 0, tzinfo=UTC)
    assert (
        client._window_coverage_metrics(
            expected_start=expected,
            actual_start=expected + datetime.resolution,
        )[0]
        == 0
    )
    assert client._as_utc(datetime(2026, 2, 6, 8, 0, tzinfo=UTC).replace(tzinfo=None)) == datetime(
        2026, 2, 6, 8, 0, tzinfo=UTC
    )
    assert client._resolve_success_window_end(
        source=SimpleNamespace(ingestion_window_end_at=datetime(2026, 2, 6, 9, 0, tzinfo=UTC)),
        fallback_window_end=now,
        max_processed_published_at=datetime(2026, 2, 6, 8, 0, tzinfo=UTC),
    ) == datetime(2026, 2, 6, 9, 0, tzinfo=UTC)
    assert client._backoff_seconds(0) >= 1.0
    assert client._is_transient_failure(httpx.ReadTimeout("timeout")) is True
    assert (
        client._is_transient_failure(
            httpx.HTTPStatusError(
                "bad",
                request=MagicMock(),
                response=SimpleNamespace(status_code=400),
            )
        )
        is False
    )


@pytest.mark.asyncio
async def test_collect_query_break_conditions_and_source_record_updates(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    query = GDELTQueryConfig(name="q", query="ukraine", max_records_per_page=2, max_pages=2)
    source = SimpleNamespace(error_count=2, last_error="bad", ingestion_window_end_at=None)
    monkeypatch.setattr(client, "_get_or_create_source", AsyncMock(return_value=source))
    monkeypatch.setattr(
        client,
        "_fetch_articles",
        AsyncMock(
            return_value=[{"url": "https://example.com/1"}, {"url": "https://example.com/2"}]
        ),
    )
    monkeypatch.setattr(client, "_matches_filters", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        client, "_store_article", AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    )
    monkeypatch.setattr(client, "_oldest_published_at", lambda *_args, **_kwargs: None)

    result = await client.collect_query(query)
    assert result.pages_fetched == 1

    await client._record_source_success(source, window_end=datetime.now(tz=UTC))
    assert source.error_count == 0
    assert source.last_error is None
    await client._record_source_failure(source, "x" * 1200)
    assert len(source.last_error) == 1000


@pytest.mark.asyncio
async def test_collect_query_breaks_on_empty_page_and_non_regressing_window_end(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    query = GDELTQueryConfig(name="q", query="ukraine", max_records_per_page=2, max_pages=2)
    source = SimpleNamespace(error_count=0, ingestion_window_end_at=None)
    monkeypatch.setattr(client, "_get_or_create_source", AsyncMock(return_value=source))
    monkeypatch.setattr(client, "_fetch_articles", AsyncMock(return_value=[]))
    monkeypatch.setattr(client, "_record_source_success", AsyncMock(return_value=None))
    monkeypatch.setattr(client, "_record_source_failure", AsyncMock(return_value=None))

    result = await client.collect_query(query)
    assert result.pages_fetched == 0

    pages = [[{"url": "https://example.com/1", "seendate": "20260206T103000Z"}]]

    async def _fetch_articles(**_kwargs):
        return pages.pop(0) if pages else []

    monkeypatch.setattr(client, "_fetch_articles", AsyncMock(side_effect=_fetch_articles))
    monkeypatch.setattr(client, "_matches_filters", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        client, "_store_article", AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    )
    monkeypatch.setattr(
        client,
        "_oldest_published_at",
        lambda *_args, **_kwargs: datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
    )
    result = await client.collect_query(query)
    assert result.pages_fetched == 1

    future_pages = [[{"url": "https://example.com/1"}, {"url": "https://example.com/2"}]]

    async def _future_fetch(**_kwargs):
        return future_pages.pop(0) if future_pages else []

    monkeypatch.setattr(client, "_fetch_articles", AsyncMock(side_effect=_future_fetch))
    monkeypatch.setattr(
        client,
        "_oldest_published_at",
        lambda *_args, **_kwargs: datetime.now(tz=UTC) + timedelta(hours=1),
    )
    result = await client.collect_query(query)
    assert result.pages_fetched == 1


def test_matches_filters_rejects_unknown_article_language() -> None:
    article = {"language": "   "}
    query = GDELTQueryConfig(name="q", languages=["en"])
    assert GDELTClient._matches_filters(article, query) is False
