"""add event adjudications

Revision ID: 0037_add_event_adjudications
Revises: 0036_add_novelty_candidates
Create Date: 2026-03-25 22:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0037_add_event_adjudications"
down_revision = "0036_add_novelty_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_adjudications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("review_status", sa.String(length=50), nullable=False),
        sa.Column("override_intent", sa.String(length=50), nullable=False),
        sa.Column(
            "resulting_effect",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('confirm', 'suppress', 'restate', 'escalate_taxonomy_review')",
            name="check_event_adjudications_outcome_allowed",
        ),
        sa.CheckConstraint(
            "review_status IN ('resolved', 'needs_taxonomy_review')",
            name="check_event_adjudications_review_status_allowed",
        ),
        sa.CheckConstraint(
            "override_intent IN ('pin_event', 'suppress_event', 'apply_restatement', 'taxonomy_escalation')",
            name="check_event_adjudications_override_intent_allowed",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feedback_id"], ["human_feedback.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_event_adjudications_event_created",
        "event_adjudications",
        ["event_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_event_adjudications_review_status_created",
        "event_adjudications",
        ["review_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_event_adjudications_feedback",
        "event_adjudications",
        ["feedback_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_event_adjudications_feedback", table_name="event_adjudications")
    op.drop_index(
        "idx_event_adjudications_review_status_created",
        table_name="event_adjudications",
    )
    op.drop_index("idx_event_adjudications_event_created", table_name="event_adjudications")
    op.drop_table("event_adjudications")
