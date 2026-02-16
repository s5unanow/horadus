"""Add per-source ingestion high-water timestamp.

Revision ID: 0012_source_ingestion_watermark
Revises: 0011_report_grounding_metadata
Create Date: 2026-02-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0012_source_ingestion_watermark"
down_revision = "0011_report_grounding_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("ingestion_window_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_sources_ingestion_window_end_at",
        "sources",
        ["ingestion_window_end_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_sources_ingestion_window_end_at", table_name="sources")
    op.drop_column("sources", "ingestion_window_end_at")
