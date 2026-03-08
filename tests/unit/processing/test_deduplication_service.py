from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.config import settings
from src.processing.deduplication_service import DeduplicationService

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_find_duplicate_matches_external_id_first(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session)
    matched_id = uuid4()
    mock_db_session.scalar.side_effect = [matched_id]

    result = await service.find_duplicate(
        external_id="item-1",
        url="https://example.com/item-1",
        content_hash="deadbeef",
    )

    assert result.is_duplicate is True
    assert result.matched_item_id == matched_id
    assert result.match_reason == "external_id"
    assert mock_db_session.scalar.await_count == 1


@pytest.mark.asyncio
async def test_find_duplicate_matches_url_when_external_id_missing(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session)
    matched_id = uuid4()
    mock_db_session.scalar.side_effect = [None, matched_id]

    result = await service.find_duplicate(
        external_id="item-1",
        url="https://www.Example.com/item-1/?utm=1#frag",
    )

    assert result.is_duplicate is True
    assert result.matched_item_id == matched_id
    assert result.match_reason == "url"
    assert mock_db_session.scalar.await_count == 2


@pytest.mark.asyncio
async def test_find_duplicate_matches_content_hash(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session)
    matched_id = uuid4()
    mock_db_session.scalar.side_effect = [None, None, matched_id]

    result = await service.find_duplicate(
        external_id="item-1",
        url="https://example.com/item-1",
        content_hash="abc123",
    )

    assert result.is_duplicate is True
    assert result.matched_item_id == matched_id
    assert result.match_reason == "content_hash"
    assert mock_db_session.scalar.await_count == 3


@pytest.mark.asyncio
async def test_find_duplicate_matches_embedding_similarity(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session, similarity_threshold=0.92)
    matched_id = uuid4()
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: (matched_id, 0.07))

    result = await service.find_duplicate(
        embedding=[0.1, 0.2, 0.3],
        embedding_model="text-embedding-3-small",
    )

    assert result.is_duplicate is True
    assert result.matched_item_id == matched_id
    assert result.match_reason == "embedding"
    assert result.similarity == pytest.approx(0.93)
    assert mock_db_session.execute.await_count == 1
    query = mock_db_session.execute.await_args.args[0]
    assert "raw_items.embedding_model =" in str(query)


@pytest.mark.asyncio
async def test_find_duplicate_strips_embedding_model_before_similarity_lookup(
    mock_db_session,
) -> None:
    service = DeduplicationService(session=mock_db_session, similarity_threshold=0.92)
    mock_db_session.scalar.side_effect = [None, None, None]
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: None)

    result = await service.find_duplicate(
        embedding=[0.1, 0.2, 0.3],
        embedding_model=" text-embedding-3-small ",
    )

    assert result.is_duplicate is False
    query = mock_db_session.execute.await_args.args[0]
    assert query.compile().params["embedding_model_1"] == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_find_duplicate_skips_embedding_similarity_without_model(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session, similarity_threshold=0.92)
    mock_db_session.scalar.side_effect = [None, None, None]

    result = await service.find_duplicate(embedding=[0.1, 0.2, 0.3])

    assert result.is_duplicate is False
    assert result.match_reason is None
    assert mock_db_session.execute.await_count == 0


@pytest.mark.asyncio
async def test_find_duplicate_returns_false_when_no_matches(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session)
    mock_db_session.scalar.side_effect = [None, None, None]
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: None)

    result = await service.find_duplicate(
        external_id="item-1",
        url="https://example.com/item-1",
        content_hash="abc123",
        embedding=[0.1, 0.2, 0.3],
    )

    assert result.is_duplicate is False
    assert result.matched_item_id is None
    assert result.match_reason is None
    assert result.similarity is None


@pytest.mark.asyncio
async def test_find_duplicate_rejects_invalid_similarity_threshold(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session, similarity_threshold=1.5)

    with pytest.raises(ValueError, match="between 0 and 1"):
        await service.find_duplicate(content_hash="abc123")


def test_normalize_url_removes_tracking_components() -> None:
    normalized = DeduplicationService.normalize_url("https://www.Example.com/path/?utm=1#frag")
    assert normalized == "https://example.com/path"


def test_normalize_url_preserves_non_tracking_query_params_sorted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEDUP_URL_QUERY_MODE", "keep_non_tracking")
    monkeypatch.setattr(settings, "DEDUP_URL_TRACKING_PARAM_PREFIXES", ["utm_"])
    monkeypatch.setattr(settings, "DEDUP_URL_TRACKING_PARAMS", ["fbclid"])

    normalized = DeduplicationService.normalize_url(
        "https://example.com/path?b=2&utm_source=x&a=1&fbclid=abc"
    )

    assert normalized == "https://example.com/path?a=1&b=2"


def test_normalize_url_strip_all_mode_removes_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEDUP_URL_QUERY_MODE", "strip_all")

    normalized = DeduplicationService.normalize_url("https://example.com/path?article=123&v=1")

    assert normalized == "https://example.com/path"


def test_compute_content_hash_returns_sha256_hex() -> None:
    digest = DeduplicationService.compute_content_hash("hello")
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_find_duplicate_excludes_current_item_id(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session)
    mock_db_session.scalar.side_effect = [None]
    excluded_id = uuid4()

    result = await service.find_duplicate(
        external_id="item-1",
        exclude_item_id=excluded_id,
    )

    assert result.is_duplicate is False
    query = mock_db_session.scalar.await_args.args[0]
    assert "raw_items.id !=" in str(query)


@pytest.mark.asyncio
async def test_is_duplicate_wrapper_and_internal_helpers(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session)
    mock_db_session.scalar.side_effect = [uuid4()]

    assert await service.is_duplicate(external_id="item-1") is True
    assert await service._find_exact_match(SimpleNamespace(), None, datetime.now(tz=UTC)) is None

    with pytest.raises(ValueError, match="must not be empty"):
        await service._find_embedding_match(
            embedding=[],
            embedding_model="text-embedding-3-small",
            window_start=datetime.now(tz=UTC),
            similarity_threshold=0.9,
        )


def test_normalize_url_handles_invalid_urls_and_non_default_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEDUP_URL_QUERY_MODE", "keep_non_tracking")
    monkeypatch.setattr(settings, "DEDUP_URL_TRACKING_PARAM_PREFIXES", ["utm_"])
    monkeypatch.setattr(settings, "DEDUP_URL_TRACKING_PARAMS", ["fbclid"])

    assert DeduplicationService.normalize_url(None) is None
    assert DeduplicationService.normalize_url("not-a-url") is None
    original_urlsplit = DeduplicationService.normalize_url.__globals__["urlsplit"]
    monkeypatch.setattr(
        "src.processing.deduplication_service.urlsplit",
        lambda _url: (_ for _ in ()).throw(ValueError("bad")),
    )
    assert DeduplicationService.normalize_url("https://example.com") is None
    monkeypatch.setattr("src.processing.deduplication_service.urlsplit", original_urlsplit)
    assert (
        DeduplicationService.normalize_url("https://www.example.com:8443/path/?=x&utm_source=a&b=2")
        == "https://example.com:8443/path?b=2"
    )
    assert (
        DeduplicationService.normalize_url("https://www.example.com:443/path/?b=2")
        == "https://example.com/path?b=2"
    )


@pytest.mark.asyncio
async def test_find_embedding_match_excludes_current_item_id(mock_db_session) -> None:
    service = DeduplicationService(session=mock_db_session)
    mock_db_session.execute.return_value = SimpleNamespace(first=lambda: None)
    excluded_id = uuid4()

    assert (
        await service._find_embedding_match(
            embedding=[0.1, 0.2],
            embedding_model="text-embedding-3-small",
            window_start=datetime.now(tz=UTC),
            similarity_threshold=0.9,
            exclude_item_id=excluded_id,
        )
        is None
    )
    query = mock_db_session.execute.await_args.args[0]
    assert "raw_items.id !=" in str(query)
