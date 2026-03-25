"""Persistence models for the novelty candidate lane."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.storage.base import Base

if TYPE_CHECKING:
    from src.storage.models import Event, RawItem

NOVELTY_CANDIDATE_KIND_VALUES = ("near_threshold_item", "event_gap")


def _sql_string_literals(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


NOVELTY_CANDIDATE_KIND_SQL_VALUES = _sql_string_literals(NOVELTY_CANDIDATE_KIND_VALUES)


class NoveltyCandidate(Base):
    """Persistent novelty candidate surfaced outside the active trend lane."""

    __tablename__ = "novelty_candidates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    cluster_key: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
    )
    raw_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_items.id", ondelete="SET NULL"),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    recurrence_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    distinct_source_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    actor_location_hits: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    near_threshold_hits: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    unmapped_signal_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    last_tier1_max_relevance: Mapped[int | None] = mapped_column(Integer)
    ranking_score: Mapped[float] = mapped_column(
        Numeric(8, 4),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[Event | None] = relationship()
    raw_item: Mapped[RawItem | None] = relationship()

    __table_args__ = (
        CheckConstraint(
            f"candidate_kind IN ({NOVELTY_CANDIDATE_KIND_SQL_VALUES})",
            name="check_novelty_candidates_kind_allowed",
        ),
        UniqueConstraint("cluster_key", name="uq_novelty_candidates_cluster_key"),
        Index("idx_novelty_candidates_last_seen", "last_seen_at"),
        Index("idx_novelty_candidates_kind_last_seen", "candidate_kind", "last_seen_at"),
        Index("idx_novelty_candidates_rank_last_seen", "ranking_score", "last_seen_at"),
        Index("idx_novelty_candidates_event", "event_id"),
        Index("idx_novelty_candidates_raw_item", "raw_item_id"),
    )
