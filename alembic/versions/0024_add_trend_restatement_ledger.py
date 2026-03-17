"""Add append-only compensating restatement ledger for trend corrections.

Revision ID: 0024_trend_restatement_ledger
Revises: 0023_event_claim_identity
Create Date: 2026-03-17
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0024_trend_restatement_ledger"
down_revision = "0023_event_claim_identity"
branch_labels = None
depends_on = None


def _trend_restatements_table() -> sa.Table:
    return sa.table(
        "trend_restatements",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("trend_id", postgresql.UUID(as_uuid=True)),
        sa.column("event_id", postgresql.UUID(as_uuid=True)),
        sa.column("event_claim_id", postgresql.UUID(as_uuid=True)),
        sa.column("trend_evidence_id", postgresql.UUID(as_uuid=True)),
        sa.column("feedback_id", postgresql.UUID(as_uuid=True)),
        sa.column("restatement_kind", sa.String(length=50)),
        sa.column("source", sa.String(length=50)),
        sa.column("original_evidence_delta_log_odds", sa.Numeric(10, 6)),
        sa.column("compensation_delta_log_odds", sa.Numeric(10, 6)),
        sa.column("notes", sa.Text()),
        sa.column("details", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("recorded_at", sa.DateTime(timezone=True)),
    )


def _backfill_legacy_invalidations() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                te.trend_id,
                te.event_id,
                te.event_claim_id,
                te.id AS trend_evidence_id,
                te.invalidation_feedback_id AS feedback_id,
                te.delta_log_odds,
                COALESCE(te.invalidated_at, hf.created_at, te.created_at) AS recorded_at,
                hf.notes
            FROM trend_evidence AS te
            LEFT JOIN human_feedback AS hf
                ON hf.id = te.invalidation_feedback_id
            WHERE te.is_invalidated = true
            """
        )
    ).mappings()
    payload = [
        {
            "id": uuid4(),
            "trend_id": row["trend_id"],
            "event_id": row["event_id"],
            "event_claim_id": row["event_claim_id"],
            "trend_evidence_id": row["trend_evidence_id"],
            "feedback_id": row["feedback_id"],
            "restatement_kind": "full_invalidation",
            "source": "event_feedback",
            "original_evidence_delta_log_odds": row["delta_log_odds"],
            "compensation_delta_log_odds": -Decimal(str(row["delta_log_odds"])),
            "notes": row["notes"],
            "details": {
                "backfilled_from_legacy_lineage": True,
                "event_action": "invalidate",
            },
            "recorded_at": row["recorded_at"],
        }
        for row in rows
    ]
    if payload:
        op.bulk_insert(_trend_restatements_table(), payload)


def _backfill_legacy_trend_overrides() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                id AS feedback_id,
                target_id AS trend_id,
                notes,
                created_at,
                corrected_value ->> 'delta_log_odds' AS delta_log_odds
            FROM human_feedback
            WHERE target_type = 'trend'
              AND action = 'override_delta'
              AND corrected_value IS NOT NULL
              AND corrected_value ? 'delta_log_odds'
            """
        )
    ).mappings()
    payload = [
        {
            "id": uuid4(),
            "trend_id": row["trend_id"],
            "event_id": None,
            "event_claim_id": None,
            "trend_evidence_id": None,
            "feedback_id": row["feedback_id"],
            "restatement_kind": "manual_compensation",
            "source": "trend_override",
            "original_evidence_delta_log_odds": None,
            "compensation_delta_log_odds": Decimal(str(row["delta_log_odds"])),
            "notes": row["notes"],
            "details": {
                "backfilled_from_legacy_lineage": True,
                "feedback_action": "override_delta",
            },
            "recorded_at": row["created_at"],
        }
        for row in rows
    ]
    if payload:
        op.bulk_insert(_trend_restatements_table(), payload)


def upgrade() -> None:
    op.create_table(
        "trend_restatements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trend_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trend_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    _backfill_legacy_invalidations()
    _backfill_legacy_trend_overrides()


def downgrade() -> None:
    op.drop_index("idx_trend_restatements_feedback", table_name="trend_restatements")
    op.drop_index("idx_trend_restatements_evidence", table_name="trend_restatements")
    op.drop_index("idx_trend_restatements_trend_recorded", table_name="trend_restatements")
    op.drop_table("trend_restatements")
