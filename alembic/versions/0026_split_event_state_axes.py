"""Split event epistemic and activity state axes.

Revision ID: 0026_split_event_state_axes
Revises: 0025_extend_taxonomy_gap_reasons
Create Date: 2026-03-20 15:25:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0026_split_event_state_axes"
down_revision = "0025_extend_taxonomy_gap_reasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "epistemic_state",
            sa.String(length=20),
            nullable=True,
            server_default="emerging",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "activity_state",
            sa.String(length=20),
            nullable=True,
            server_default="active",
        ),
    )
    op.execute(
        """
        UPDATE events
        SET activity_state = CASE lifecycle_status
            WHEN 'archived' THEN 'closed'
            WHEN 'fading' THEN 'dormant'
            ELSE 'active'
        END
        """
    )
    op.execute(
        """
        UPDATE events
        SET epistemic_state = CASE
            WHEN EXISTS (
                SELECT 1
                FROM human_feedback AS hf
                WHERE hf.target_type = 'event'
                  AND hf.target_id = events.id
                  AND hf.action IN ('mark_noise', 'invalidate')
            ) THEN 'retracted'
            WHEN lifecycle_status IN ('fading', 'archived') THEN 'confirmed'
            WHEN has_contradictions = true THEN 'contested'
            WHEN lifecycle_status = 'emerging' THEN 'emerging'
            ELSE 'confirmed'
        END
        """
    )
    op.alter_column("events", "epistemic_state", nullable=False)
    op.alter_column("events", "activity_state", nullable=False)
    op.alter_column("events", "epistemic_state", server_default=None)
    op.alter_column("events", "activity_state", server_default=None)
    op.create_check_constraint(
        "check_events_epistemic_state_allowed",
        "events",
        "epistemic_state IN ('emerging', 'confirmed', 'contested', 'retracted')",
    )
    op.create_check_constraint(
        "check_events_activity_state_allowed",
        "events",
        "activity_state IN ('active', 'dormant', 'closed')",
    )
    op.create_index("idx_events_activity", "events", ["activity_state", "last_mention_at"])


def downgrade() -> None:
    op.drop_index("idx_events_activity", table_name="events")
    op.drop_constraint("check_events_activity_state_allowed", "events", type_="check")
    op.drop_constraint("check_events_epistemic_state_allowed", "events", type_="check")
    op.drop_column("events", "activity_state")
    op.drop_column("events", "epistemic_state")
