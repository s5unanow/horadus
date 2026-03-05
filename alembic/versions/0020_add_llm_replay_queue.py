"""Add bounded LLM replay queue for degraded-mode recovery.

Revision ID: 0020_llm_replay_queue
Revises: 0019_trend_evidence_factors
Create Date: 2026-03-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0020_llm_replay_queue"
down_revision = "0019_trend_evidence_factors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_replay_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','done','error')",
            name="check_llm_replay_queue_status_allowed",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stage", "event_id", name="uq_llm_replay_stage_event"),
    )
    op.create_index(
        "idx_llm_replay_status_enqueued",
        "llm_replay_queue",
        ["status", "enqueued_at"],
        unique=False,
    )
    op.create_index(
        "idx_llm_replay_event",
        "llm_replay_queue",
        ["event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_llm_replay_event", table_name="llm_replay_queue")
    op.drop_index("idx_llm_replay_status_enqueued", table_name="llm_replay_queue")
    op.drop_table("llm_replay_queue")
