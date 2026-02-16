"""Add grounding metadata columns for generated report narratives.

Revision ID: 0011_report_grounding_metadata
Revises: 0010_embedding_lineage
Create Date: 2026-02-16
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_report_grounding_metadata"
down_revision = "0010_embedding_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "grounding_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_checked",
        ),
    )
    op.add_column(
        "reports",
        sa.Column(
            "grounding_violation_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "reports",
        sa.Column("grounding_references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.alter_column("reports", "grounding_status", server_default=None)
    op.alter_column("reports", "grounding_violation_count", server_default=None)


def downgrade() -> None:
    op.drop_column("reports", "grounding_references")
    op.drop_column("reports", "grounding_violation_count")
    op.drop_column("reports", "grounding_status")
