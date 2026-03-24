"""Add persisted source coverage snapshots.

Revision ID: 0034_add_coverage_snapshots
Revises: 0033_event_provisional_state
Create Date: 2026-03-24
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0034_add_coverage_snapshots"
down_revision = "0033_event_provisional_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coverage_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lookback_hours", sa.Integer(), nullable=False),
        sa.Column("artifact_path", sa.String(length=512), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_coverage_snapshots_generated_at",
        "coverage_snapshots",
        ["generated_at"],
        unique=False,
    )
    op.create_index(
        "idx_coverage_snapshots_window_end",
        "coverage_snapshots",
        ["window_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_coverage_snapshots_window_end", table_name="coverage_snapshots")
    op.drop_index("idx_coverage_snapshots_generated_at", table_name="coverage_snapshots")
    op.drop_table("coverage_snapshots")
