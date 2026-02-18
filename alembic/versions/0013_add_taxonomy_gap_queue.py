"""Add taxonomy gap queue for runtime mismatch triage.

Revision ID: 0013_taxonomy_gap_queue
Revises: 0012_source_ingestion_watermark
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_taxonomy_gap_queue"
down_revision = "0012_source_ingestion_watermark"
branch_labels = None
depends_on = None


def upgrade() -> None:
    taxonomy_gap_reason = postgresql.ENUM(
        "unknown_trend_id",
        "unknown_signal_type",
        name="taxonomy_gap_reason",
        create_type=False,
    )
    taxonomy_gap_status = postgresql.ENUM(
        "open",
        "resolved",
        "rejected",
        name="taxonomy_gap_status",
        create_type=False,
    )
    taxonomy_gap_reason.create(op.get_bind(), checkfirst=True)
    taxonomy_gap_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "taxonomy_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trend_id", sa.String(length=255), nullable=False),
        sa.Column("signal_type", sa.String(length=255), nullable=False),
        sa.Column("reason", taxonomy_gap_reason, nullable=False),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'pipeline'"),
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            taxonomy_gap_status,
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_taxonomy_gaps_observed_at",
        "taxonomy_gaps",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        "idx_taxonomy_gaps_status_observed",
        "taxonomy_gaps",
        ["status", "observed_at"],
        unique=False,
    )
    op.create_index(
        "idx_taxonomy_gaps_reason",
        "taxonomy_gaps",
        ["reason"],
        unique=False,
    )
    op.create_index(
        "idx_taxonomy_gaps_trend_signal",
        "taxonomy_gaps",
        ["trend_id", "signal_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_taxonomy_gaps_trend_signal", table_name="taxonomy_gaps")
    op.drop_index("idx_taxonomy_gaps_reason", table_name="taxonomy_gaps")
    op.drop_index("idx_taxonomy_gaps_status_observed", table_name="taxonomy_gaps")
    op.drop_index("idx_taxonomy_gaps_observed_at", table_name="taxonomy_gaps")
    op.drop_table("taxonomy_gaps")

    taxonomy_gap_status = postgresql.ENUM(name="taxonomy_gap_status")
    taxonomy_gap_reason = postgresql.ENUM(name="taxonomy_gap_reason")
    taxonomy_gap_status.drop(op.get_bind(), checkfirst=True)
    taxonomy_gap_reason.drop(op.get_bind(), checkfirst=True)
