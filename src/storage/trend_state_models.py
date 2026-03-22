"""Versioned live-state models for trend activation lineage."""

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.storage.base import Base
from src.storage.scoring_contract import (
    TREND_SCORING_MATH_VERSION,
    TREND_SCORING_PARAMETER_SET,
)

if TYPE_CHECKING:
    from src.storage.models import Trend

TREND_STATE_ACTIVATION_SQL_VALUES = "'create', 'rebase', 'replay', 'new_line'"


class TrendDefinitionVersion(Base):
    """Append-only record of trend definition payload changes."""

    __tablename__ = "trend_definition_versions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        nullable=False,
    )
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255))
    context: Mapped[str | None] = mapped_column(String(255))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    trend: Mapped[Trend] = relationship(
        "Trend",
        back_populates="definition_versions",
        foreign_keys=[trend_id],
    )

    __table_args__ = (
        Index("idx_trend_definition_versions_trend_recorded", "trend_id", "recorded_at"),
        Index("idx_trend_definition_versions_hash", "definition_hash"),
    )


class TrendStateVersion(Base):
    """Append-only live-state lineage for one trend contract activation."""

    __tablename__ = "trend_state_versions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_state_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trend_state_versions.id", ondelete="SET NULL"),
    )
    definition_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trend_definition_versions.id", ondelete="SET NULL"),
    )
    definition_hash: Mapped[str | None] = mapped_column(String(64))
    activation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scoring_math_version: Mapped[str] = mapped_column(
        String(64),
        default=TREND_SCORING_MATH_VERSION,
        server_default=text(f"'{TREND_SCORING_MATH_VERSION}'"),
        nullable=False,
    )
    scoring_parameter_set: Mapped[str] = mapped_column(
        String(64),
        default=TREND_SCORING_PARAMETER_SET,
        server_default=text(f"'{TREND_SCORING_PARAMETER_SET}'"),
        nullable=False,
    )
    baseline_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    starting_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    current_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    decay_half_life_days: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255))
    context: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    trend: Mapped[Trend] = relationship(
        "Trend",
        back_populates="state_versions",
        foreign_keys=[trend_id],
    )
    parent_state_version: Mapped[TrendStateVersion | None] = relationship(
        remote_side=[id],
        foreign_keys=[parent_state_version_id],
    )
    definition_version: Mapped[TrendDefinitionVersion | None] = relationship(
        "TrendDefinitionVersion", foreign_keys=[definition_version_id]
    )

    __table_args__ = (
        CheckConstraint(
            f"activation_kind IN ({TREND_STATE_ACTIVATION_SQL_VALUES})",
            name="check_trend_state_versions_activation_kind_allowed",
        ),
        Index("idx_trend_state_versions_trend_activated", "trend_id", "activated_at"),
        Index("idx_trend_state_versions_definition", "definition_version_id"),
    )
