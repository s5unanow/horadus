"""Add append-only compensating restatement ledger for trend corrections.

Revision ID: 0024_trend_restatement_ledger
Revises: 0023_event_claim_identity
Create Date: 2026-03-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0024_trend_restatement_ledger"
down_revision = "0023_event_claim_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_restatements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trend_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trend_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("replacement_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("restatement_kind", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("original_evidence_delta_log_odds", sa.Numeric(10, 6), nullable=True),
        sa.Column("compensation_delta_log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "restatement_kind IN ('full_invalidation', 'partial_restatement', 'manual_compensation', 'reclassification')",
            name="check_trend_restatements_kind_allowed",
        ),
        sa.CheckConstraint(
            "source IN ('event_feedback', 'trend_override', 'tier2_reconciliation')",
            name="check_trend_restatements_source_allowed",
        ),
        sa.ForeignKeyConstraint(["event_claim_id"], ["event_claims.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["feedback_id"], ["human_feedback.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["replacement_evidence_id"],
            ["trend_evidence.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["trend_evidence_id"], ["trend_evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trend_id"], ["trends.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_trend_restatements_trend_recorded",
        "trend_restatements",
        ["trend_id", "recorded_at"],
    )
    op.create_index(
        "idx_trend_restatements_evidence",
        "trend_restatements",
        ["trend_evidence_id"],
    )
    op.create_index(
        "idx_trend_restatements_feedback",
        "trend_restatements",
        ["feedback_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_trend_restatements_feedback", table_name="trend_restatements")
    op.drop_index("idx_trend_restatements_evidence", table_name="trend_restatements")
    op.drop_index("idx_trend_restatements_trend_recorded", table_name="trend_restatements")
    op.drop_table("trend_restatements")
