"""Add processing_started_at column for stale-item recovery.

Revision ID: 0005_add_processing_started_at
Revises: 0004_add_api_usage_table
Create Date: 2026-02-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_add_processing_started_at"
down_revision = "0004_add_api_usage_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_items",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_raw_items_processing_started_at",
        "raw_items",
        ["processing_started_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_raw_items_processing_started_at", table_name="raw_items")
    op.drop_column("raw_items", "processing_started_at")
