"""Add append-only trend definition version history table.

Revision ID: 0017_trend_definition_versions
Revises: 0016_event_item_unique_item
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0017_trend_definition_versions"
down_revision = "0016_event_item_unique_item"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_definition_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trend_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("context", sa.String(length=255), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["trend_id"], ["trends.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_trend_definition_versions_trend_recorded",
        "trend_definition_versions",
        ["trend_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "idx_trend_definition_versions_hash",
        "trend_definition_versions",
        ["definition_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_trend_definition_versions_hash", table_name="trend_definition_versions")
    op.drop_index(
        "idx_trend_definition_versions_trend_recorded",
        table_name="trend_definition_versions",
    )
    op.drop_table("trend_definition_versions")
