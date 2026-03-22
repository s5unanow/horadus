"""Feedback and restatement ledger models extracted from the main model module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.base import Base
from src.storage.scoring_contract import (
    TREND_SCORING_MATH_VERSION,
    TREND_SCORING_PARAMETER_SET,
)

RESTATEMENT_KIND_SQL_VALUES = (
    "'full_invalidation', 'partial_restatement', 'manual_compensation', 'reclassification'"
)
RESTATEMENT_SOURCE_SQL_VALUES = "'event_feedback', 'trend_override', 'tier2_reconciliation'"


class HumanFeedback(Base):
    """Human corrections and annotations used for governance and replay lineage."""

    __tablename__ = "human_feedback"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    original_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    corrected_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_feedback_target", "target_type", "target_id"),
        Index("idx_feedback_action", "action"),
    )


class PrivilegedWriteAudit(Base):
    """Durable audit and idempotency record for privileged API writes."""

    __tablename__ = "privileged_write_audits"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_key: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_api_key_id: Mapped[str | None] = mapped_column(String(255))
    actor_api_key_name: Mapped[str | None] = mapped_column(String(255))
    operator_identity: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    request_method: Mapped[str] = mapped_column(String(10), nullable=False)
    request_path: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_identifier: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_intent: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    expected_revision_token: Mapped[str | None] = mapped_column(String(128))
    observed_revision_token: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    result_links: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    replay_count: Mapped[int] = mapped_column(
        Integer,
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

    __table_args__ = (
        Index("idx_privileged_write_audits_action_seen", "action", "first_seen_at"),
        Index("idx_privileged_write_audits_target", "target_type", "target_identifier"),
        Index(
            "uq_privileged_write_audits_actor_action_idempotency",
            "actor_key",
            "action",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class TrendRestatement(Base):
    """Append-only compensating deltas applied after original evidence scoring."""

    __tablename__ = "trend_restatements"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    trend_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
    )
    event_claim_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_claims.id", ondelete="SET NULL"),
    )
    trend_evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trend_evidence.id", ondelete="SET NULL"),
    )
    state_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("trend_state_versions.id", ondelete="SET NULL"),
    )
    feedback_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("human_feedback.id", ondelete="SET NULL"),
    )
    restatement_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    original_evidence_delta_log_odds: Mapped[float | None] = mapped_column(Numeric(10, 6))
    compensation_delta_log_odds: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
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
    notes: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            f"restatement_kind IN ({RESTATEMENT_KIND_SQL_VALUES})",
            name="check_trend_restatements_kind_allowed",
        ),
        CheckConstraint(
            f"source IN ({RESTATEMENT_SOURCE_SQL_VALUES})",
            name="check_trend_restatements_source_allowed",
        ),
        Index("idx_trend_restatements_trend_recorded", "trend_id", "recorded_at"),
        Index("idx_trend_restatements_state_recorded", "state_version_id", "recorded_at"),
        Index("idx_trend_restatements_evidence", "trend_evidence_id"),
        Index("idx_trend_restatements_feedback", "feedback_id"),
    )
