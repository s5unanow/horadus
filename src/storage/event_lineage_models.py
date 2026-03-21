"""Event split/merge lineage models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.base import Base

EVENT_LINEAGE_KIND_SQL_VALUES = "'merge', 'split'"


class EventLineage(Base):
    """Append-only audit rows for event split and merge repairs."""

    __tablename__ = "event_lineage"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    lineage_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
    )
    target_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            f"lineage_kind IN ({EVENT_LINEAGE_KIND_SQL_VALUES})",
            name="check_event_lineage_kind_allowed",
        ),
        Index("idx_event_lineage_source_created", "source_event_id", "created_at"),
        Index("idx_event_lineage_target_created", "target_event_id", "created_at"),
    )
