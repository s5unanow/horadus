"""Add persistent novelty lane candidates.

Revision ID: 0036_add_novelty_candidates
Revises: 0035_add_source_provider_keys
Create Date: 2026-03-25 21:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0036_add_novelty_candidates"
down_revision = "0035_add_source_provider_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "novelty_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_key", sa.String(length=64), nullable=False),
        sa.Column("candidate_kind", sa.String(length=32), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("recurrence_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "distinct_source_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "actor_location_hits",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "near_threshold_hits",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "unmapped_signal_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_tier1_max_relevance", sa.Integer(), nullable=True),
        sa.Column("ranking_score", sa.Numeric(precision=8, scale=4), server_default=sa.text("0"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "candidate_kind IN ('near_threshold_item', 'event_gap')",
            name="check_novelty_candidates_kind_allowed",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["raw_item_id"], ["raw_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cluster_key", name="uq_novelty_candidates_cluster_key"),
    )
    op.create_index(
        "idx_novelty_candidates_last_seen",
        "novelty_candidates",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        "idx_novelty_candidates_kind_last_seen",
        "novelty_candidates",
        ["candidate_kind", "last_seen_at"],
        unique=False,
    )
    op.create_index(
        "idx_novelty_candidates_rank_last_seen",
        "novelty_candidates",
        ["ranking_score", "last_seen_at"],
        unique=False,
    )
    op.create_index(
        "idx_novelty_candidates_event",
        "novelty_candidates",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "idx_novelty_candidates_raw_item",
        "novelty_candidates",
        ["raw_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_novelty_candidates_raw_item", table_name="novelty_candidates")
    op.drop_index("idx_novelty_candidates_event", table_name="novelty_candidates")
    op.drop_index("idx_novelty_candidates_rank_last_seen", table_name="novelty_candidates")
    op.drop_index("idx_novelty_candidates_kind_last_seen", table_name="novelty_candidates")
    op.drop_index("idx_novelty_candidates_last_seen", table_name="novelty_candidates")
    op.drop_table("novelty_candidates")
