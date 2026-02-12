"""Add temporal provenance fields to trend evidence records.

Revision ID: 0007_evidence_decay_fields
Revises: 0006_snapshot_retention
Create Date: 2026-02-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_evidence_decay_fields"
down_revision = "0006_snapshot_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trend_evidence",
        sa.Column("evidence_age_days", sa.Numeric(precision=6, scale=2), nullable=True),
    )
    op.add_column(
        "trend_evidence",
        sa.Column("temporal_decay_factor", sa.Numeric(precision=5, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trend_evidence", "temporal_decay_factor")
    op.drop_column("trend_evidence", "evidence_age_days")
