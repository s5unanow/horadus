"""Add embedding lineage metadata columns for vectors.

Revision ID: 0010_embedding_lineage
Revises: 0009_trend_baseline_sync
Create Date: 2026-02-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_embedding_lineage"
down_revision = "0009_trend_baseline_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_items", sa.Column("embedding_model", sa.String(length=255), nullable=True))
    op.add_column(
        "raw_items",
        sa.Column("embedding_generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("events", sa.Column("embedding_model", sa.String(length=255), nullable=True))
    op.add_column(
        "events",
        sa.Column("embedding_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "embedding_generated_at")
    op.drop_column("events", "embedding_model")
    op.drop_column("raw_items", "embedding_generated_at")
    op.drop_column("raw_items", "embedding_model")
