"""Storage models for persisted source-coverage snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.base import Base


class CoverageSnapshot(Base):
    """Persisted coverage-health snapshot for operational review."""

    __tablename__ = "coverage_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    lookback_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[dict[str, Any]] = mapped_column(
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

    __table_args__ = (
        Index("idx_coverage_snapshots_generated_at", "generated_at"),
        Index("idx_coverage_snapshots_window_end", "window_end"),
    )
