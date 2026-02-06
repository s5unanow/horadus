from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.ingestion.gdelt_client import GDELTClient, GDELTQueryConfig
from src.storage.models import ProcessingStatus

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_load_config_parses_settings_and_queries(
    tmp_path: Path,
    mock_db_session,
    mock_http_client,
) -> None:
    config_path = tmp_path / "gdelt.yaml"
    config_path.write_text(
        """
settings:
  request_timeout_seconds: 42
  user_agent: "test-agent"
  default_lookback_hours: 12
  default_max_records_per_page: 50
  default_max_pages: 2
queries:
  - name: "Query One"
    query: "ukraine"
    themes: ["MILITARY"]
    actors: ["NATO"]
    languages: ["english"]
    enabled: true
  - name: ""
""",
        encoding="utf-8",
    )

    client = GDELTClient(
        session=mock_db_session,
        http_client=mock_http_client,
        config_path=str(config_path),
    )

    await client.load_config(force=True)

    assert client.settings.request_timeout_seconds == 42
    assert client.settings.user_agent == "test-agent"
    assert client.settings.default_lookback_hours == 12
    assert len(client.queries) == 1
    assert client.queries[0].name == "Query One"
    assert client.queries[0].max_records_per_page == 50
    assert client.queries[0].max_pages == 2


def test_build_query_string_includes_filters() -> None:
    query = GDELTQueryConfig(
        name="Q",
        query="ukraine",
        themes=["MILITARY"],
        actors=["NATO"],
        countries=["ua"],
    )

    built = GDELTClient._build_query_string(query)

    assert "(ukraine)" in built
    assert "(theme:MILITARY)" in built
    assert '("NATO")' in built
    assert "(sourcecountry:UA)" in built


def test_matches_filters_theme_actor_language_country() -> None:
    article = {
        "themes": "MILITARY;ECONOMY",
        "persons": "NATO,UN",
        "language": "English",
        "sourcecountry": "UA",
        "title": "NATO discussed security",
    }
    query = GDELTQueryConfig(
        name="Q",
        query="ukraine",
        themes=["MILITARY"],
        actors=["NATO"],
        languages=["en"],
        countries=["UA"],
    )

    assert GDELTClient._matches_filters(article, query) is True

    bad_actor = GDELTQueryConfig(
        name="Q",
        query="ukraine",
        themes=["MILITARY"],
        actors=["OSCE"],
    )
    assert GDELTClient._matches_filters(article, bad_actor) is False


@pytest.mark.asyncio
async def test_collect_query_counts_stored_and_skipped(
    mock_db_session,
    mock_http_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    query = GDELTQueryConfig(
        name="Example Query",
        query="ukraine",
        themes=["MILITARY"],
        max_records_per_page=2,
        max_pages=2,
    )
    source = SimpleNamespace(error_count=0)
    now_utc = datetime.now(tz=UTC)
    first_seen = (now_utc - timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")
    second_seen = (now_utc - timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")
    pages = [
        [
            {"url": "https://example.com/1", "keep": True, "seendate": first_seen},
            {"url": "https://example.com/2", "keep": False, "seendate": first_seen},
        ],
        [
            {"url": "https://example.com/3", "keep": True, "seendate": second_seen},
        ],
    ]
    stored_urls: list[str] = []

    async def fake_get_or_create_source(_query: GDELTQueryConfig) -> SimpleNamespace:
        return source

    async def fake_fetch_articles(**_kwargs) -> list[dict[str, str | bool]]:
        return pages.pop(0) if pages else []

    def fake_matches_filters(article: dict[str, str | bool], _query: GDELTQueryConfig) -> bool:
        return bool(article.get("keep"))

    async def fake_store_article(*, source, article, published_at):
        url = str(article.get("url"))
        if url.endswith("/3"):
            return None
        stored_urls.append(url)
        return SimpleNamespace(id=uuid4())

    async def fake_record_success(_source) -> None:
        return None

    async def fake_record_failure(_source, _error: str) -> None:
        return None

    monkeypatch.setattr(client, "_get_or_create_source", fake_get_or_create_source)
    monkeypatch.setattr(client, "_fetch_articles", fake_fetch_articles)
    monkeypatch.setattr(client, "_matches_filters", fake_matches_filters)
    monkeypatch.setattr(client, "_store_article", fake_store_article)
    monkeypatch.setattr(client, "_record_source_success", fake_record_success)
    monkeypatch.setattr(client, "_record_source_failure", fake_record_failure)

    result = await client.collect_query(query)

    assert result.query_name == "Example Query"
    assert result.pages_fetched == 2
    assert result.items_fetched == 3
    assert result.items_stored == 1
    assert result.items_skipped == 2
    assert result.errors == []
    assert stored_urls == ["https://example.com/1"]


@pytest.mark.asyncio
async def test_store_article_sets_pending_status(mock_db_session, mock_http_client) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    source = SimpleNamespace(id=uuid4())
    article = {
        "url": "https://example.com/article/1",
        "title": "Title",
        "language": "English",
        "domain": "example.com",
        "seendate": "20260206103000",
        "themes": "MILITARY",
        "persons": "NATO",
    }

    async def fake_is_duplicate(
        _normalized_url: str | None,
        _external_id: str,
        _content_hash: str,
    ) -> bool:
        return False

    client._is_duplicate = fake_is_duplicate

    item = await client._store_article(
        source=source,
        article=article,
        published_at=datetime(2026, 2, 6, 10, 30, tzinfo=UTC),
    )

    assert item is not None
    assert item.processing_status == ProcessingStatus.PENDING
    assert item.external_id == "https://example.com/article/1"
    assert item.url == "https://example.com/article/1"
    assert item.language == "en"
    assert mock_db_session.add.call_count == 1


@pytest.mark.asyncio
async def test_is_duplicate_checks_recent_window(mock_db_session, mock_http_client) -> None:
    client = GDELTClient(session=mock_db_session, http_client=mock_http_client)
    mock_db_session.scalar.return_value = uuid4()

    duplicate = await client._is_duplicate(
        normalized_url="https://example.com/article/1",
        external_id="https://example.com/article/1",
        content_hash="abc123",
    )

    assert duplicate is True
    assert mock_db_session.scalar.await_count == 1
