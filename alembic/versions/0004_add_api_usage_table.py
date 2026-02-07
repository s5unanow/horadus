"""Add api_usage table for cost tracking.

Revision ID: 0004_add_api_usage_table
Revises: 0003_add_event_embedding_index
Create Date: 2026-02-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_add_api_usage_table"
down_revision = "0003_add_event_embedding_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(10, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "tier", name="uq_api_usage_date_tier"),
    )
    op.create_index("idx_api_usage_date", "api_usage", ["date"])


def downgrade() -> None:
    op.drop_index("idx_api_usage_date", table_name="api_usage")
    op.drop_table("api_usage")
