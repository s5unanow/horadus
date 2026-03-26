"""Canonical entity registry models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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

CANONICAL_ENTITY_TYPE_SQL_VALUES = "'person', 'organization', 'location'"
EVENT_ENTITY_ROLE_SQL_VALUES = "'actor', 'location'"
ENTITY_RESOLUTION_STATUS_SQL_VALUES = "'resolved', 'ambiguous', 'unresolved'"


class CanonicalEntity(Base):
    """Durable entity row used for actor and location references."""

    __tablename__ = "canonical_entities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    is_auto_seeded: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    aliases: Mapped[list[CanonicalEntityAlias]] = relationship(
        back_populates="canonical_entity",
        cascade="all, delete-orphan",
    )
    event_links: Mapped[list[EventEntity]] = relationship(back_populates="canonical_entity")

    __table_args__ = (
        CheckConstraint(
            f"entity_type IN ({CANONICAL_ENTITY_TYPE_SQL_VALUES})",
            name="check_canonical_entities_type_allowed",
        ),
        UniqueConstraint(
            "entity_type",
            "normalized_name",
            name="uq_canonical_entities_type_normalized_name",
        ),
        Index("idx_canonical_entities_type_name", "entity_type", "normalized_name"),
    )


class CanonicalEntityAlias(Base):
    """Exact alias rows used for bounded canonical-entity resolution."""

    __tablename__ = "canonical_entity_aliases"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("canonical_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    canonical_entity: Mapped[CanonicalEntity] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint(
            "canonical_entity_id",
            "normalized_alias",
            name="uq_canonical_entity_aliases_entity_alias",
        ),
        Index("idx_canonical_entity_aliases_normalized_alias", "normalized_alias"),
    )


class EventEntity(Base):
    """Entity mention extracted for an event and linked to a canonical entity when possible."""

    __tablename__ = "event_entities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_role: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mention_text: Mapped[str] = mapped_column(Text, nullable=False)
    mention_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("canonical_entities.id", ondelete="SET NULL"),
    )
    resolution_status: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution_reason: Mapped[str | None] = mapped_column(String(40))
    resolution_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    canonical_entity: Mapped[CanonicalEntity | None] = relationship(back_populates="event_links")

    __table_args__ = (
        CheckConstraint(
            f"entity_role IN ({EVENT_ENTITY_ROLE_SQL_VALUES})",
            name="check_event_entities_role_allowed",
        ),
        CheckConstraint(
            f"entity_type IN ({CANONICAL_ENTITY_TYPE_SQL_VALUES})",
            name="check_event_entities_type_allowed",
        ),
        CheckConstraint(
            f"resolution_status IN ({ENTITY_RESOLUTION_STATUS_SQL_VALUES})",
            name="check_event_entities_resolution_status_allowed",
        ),
        UniqueConstraint(
            "event_id",
            "entity_role",
            "entity_type",
            "mention_normalized",
            name="uq_event_entities_event_mention",
        ),
        Index("idx_event_entities_event_role", "event_id", "entity_role"),
        Index("idx_event_entities_canonical_entity", "canonical_entity_id"),
    )
