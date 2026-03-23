"""Add provisional vs canonical extraction state for events.

Revision ID: 0033_event_provisional_state
Revises: 0032_add_event_summary_field
Create Date: 2026-03-23
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0033_event_provisional_state"
down_revision = "0032_add_event_summary_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "extraction_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "provisional_extraction",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "check_events_extraction_status_allowed",
        "events",
        "extraction_status IN ('none', 'canonical', 'provisional')",
    )
    op.execute(
        """
        UPDATE events
        SET extraction_status = 'canonical'
        WHERE COALESCE(extraction_provenance ->> 'status', '') != 'replay_pending'
          AND (
            COALESCE(NULLIF(BTRIM(event_summary), ''), '') != ''
            OR extracted_who IS NOT NULL
            OR COALESCE(NULLIF(BTRIM(extracted_what), ''), '') != ''
            OR COALESCE(NULLIF(BTRIM(extracted_where), ''), '') != ''
            OR extracted_when IS NOT NULL
            OR extracted_claims IS NOT NULL
            OR COALESCE(array_length(categories, 1), 0) > 0
            OR has_contradictions IS TRUE
            OR COALESCE(NULLIF(BTRIM(contradiction_notes), ''), '') != ''
            OR COALESCE(extraction_provenance ->> 'stage', '') = 'tier2'
          )
        """
    )


def downgrade() -> None:
    op.drop_constraint("check_events_extraction_status_allowed", "events", type_="check")
    op.drop_column("events", "provisional_extraction")
    op.drop_column("events", "extraction_status")
