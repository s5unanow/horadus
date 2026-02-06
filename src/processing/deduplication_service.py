"""
Deduplication service using exact and embedding-similarity checks.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.storage.models import RawItem


@dataclass(slots=True)
class DeduplicationResult:
    """Result of a duplicate lookup."""

    is_duplicate: bool
    matched_item_id: UUID | None = None
    match_reason: str | None = None
    similarity: float | None = None


class DeduplicationService:
    """Detect duplicate raw items by exact fields and embedding similarity."""

    def __init__(
        self,
        session: AsyncSession,
        similarity_threshold: float | None = None,
    ) -> None:
        self.session = session
        self.similarity_threshold = (
            settings.DEDUP_SIMILARITY_THRESHOLD
            if similarity_threshold is None
            else similarity_threshold
        )

    async def find_duplicate(
        self,
        *,
        external_id: str | None = None,
        url: str | None = None,
        content_hash: str | None = None,
        embedding: list[float] | None = None,
        dedup_window_days: int = 7,
    ) -> DeduplicationResult:
        """
        Return duplicate match details for a candidate item.
        """
        if not 0 <= self.similarity_threshold <= 1:
            msg = "similarity_threshold must be between 0 and 1"
            raise ValueError(msg)

        window_start = datetime.now(tz=UTC) - timedelta(days=dedup_window_days)
        normalized_url = self.normalize_url(url) if url is not None else None

        match_id = await self._find_exact_match(
            RawItem.external_id,
            external_id,
            window_start,
        )
        if match_id is not None:
            return DeduplicationResult(
                is_duplicate=True,
                matched_item_id=match_id,
                match_reason="external_id",
            )

        match_id = await self._find_exact_match(
            RawItem.url,
            normalized_url,
            window_start,
        )
        if match_id is not None:
            return DeduplicationResult(
                is_duplicate=True,
                matched_item_id=match_id,
                match_reason="url",
            )

        match_id = await self._find_exact_match(
            RawItem.content_hash,
            content_hash,
            window_start,
        )
        if match_id is not None:
            return DeduplicationResult(
                is_duplicate=True,
                matched_item_id=match_id,
                match_reason="content_hash",
            )

        if embedding is not None:
            embedding_match = await self._find_embedding_match(
                embedding=embedding,
                window_start=window_start,
                similarity_threshold=self.similarity_threshold,
            )
            if embedding_match is not None:
                matched_id, similarity = embedding_match
                return DeduplicationResult(
                    is_duplicate=True,
                    matched_item_id=matched_id,
                    match_reason="embedding",
                    similarity=similarity,
                )

        return DeduplicationResult(is_duplicate=False)

    async def is_duplicate(
        self,
        *,
        external_id: str | None = None,
        url: str | None = None,
        content_hash: str | None = None,
        embedding: list[float] | None = None,
        dedup_window_days: int = 7,
    ) -> bool:
        """Convenience wrapper returning only duplicate status."""
        return (
            await self.find_duplicate(
                external_id=external_id,
                url=url,
                content_hash=content_hash,
                embedding=embedding,
                dedup_window_days=dedup_window_days,
            )
        ).is_duplicate

    async def _find_exact_match(
        self,
        column: Any,
        value: str | None,
        window_start: datetime,
    ) -> UUID | None:
        if value is None:
            return None
        query = (
            select(RawItem.id)
            .where(RawItem.fetched_at >= window_start)
            .where(column == value)
            .limit(1)
        )
        matched_id: UUID | None = await self.session.scalar(query)
        return matched_id

    async def _find_embedding_match(
        self,
        *,
        embedding: list[float],
        window_start: datetime,
        similarity_threshold: float,
    ) -> tuple[UUID, float] | None:
        if not embedding:
            msg = "embedding must not be empty"
            raise ValueError(msg)

        max_distance = 1.0 - similarity_threshold
        distance_expr = RawItem.embedding.cosine_distance(embedding)

        query = (
            select(RawItem.id, distance_expr.label("distance"))
            .where(RawItem.fetched_at >= window_start)
            .where(RawItem.embedding.is_not(None))
            .where(distance_expr <= max_distance)
            .order_by(distance_expr.asc())
            .limit(1)
        )
        row = (await self.session.execute(query)).first()
        if row is None:
            return None

        matched_id = cast("UUID", row[0])
        distance = float(row[1])
        similarity = 1.0 - distance
        return (matched_id, similarity)

    @staticmethod
    def normalize_url(url: str | None) -> str | None:
        """Normalize URL by stripping fragments, query params, and default ports."""
        if url is None:
            return None
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
    def compute_content_hash(content: str) -> str:
        """Compute SHA256 hash used for exact deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
