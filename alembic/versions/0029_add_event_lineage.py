"""Add append-only event split/merge lineage ledger.

Revision ID: 0029_event_lineage
Revises: 0028_runtime_provenance_contract
Create Date: 2026-03-21 11:35:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0029_event_lineage"
down_revision = "0028_runtime_provenance_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_lineage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lineage_kind", sa.String(length=20), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "lineage_kind IN ('merge', 'split')",
            name="check_event_lineage_kind_allowed",
        ),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_event_lineage_source_created",
        "event_lineage",
        ["source_event_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_event_lineage_target_created",
        "event_lineage",
        ["target_event_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_event_lineage_target_created", table_name="event_lineage")
    op.drop_index("idx_event_lineage_source_created", table_name="event_lineage")
    op.drop_table("event_lineage")
