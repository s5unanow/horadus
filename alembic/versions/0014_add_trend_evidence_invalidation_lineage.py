"""Add trend-evidence invalidation lineage columns.

Revision ID: 0014_evidence_invalidation_lineage
Revises: 0013_taxonomy_gap_queue
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0014_evidence_invalidation_lineage"
down_revision = "0013_taxonomy_gap_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trend_evidence",
        sa.Column(
            "is_invalidated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "trend_evidence",
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trend_evidence",
        sa.Column("invalidation_feedback_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_trend_evidence_invalidation_feedback_id",
        "trend_evidence",
        "human_feedback",
        ["invalidation_feedback_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_evidence_event_invalidated",
        "trend_evidence",
        ["event_id", "is_invalidated"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_evidence_event_invalidated", table_name="trend_evidence")
    op.drop_constraint(
        "fk_trend_evidence_invalidation_feedback_id",
        "trend_evidence",
        type_="foreignkey",
    )
    op.drop_column("trend_evidence", "invalidation_feedback_id")
    op.drop_column("trend_evidence", "invalidated_at")
    op.drop_column("trend_evidence", "is_invalidated")
