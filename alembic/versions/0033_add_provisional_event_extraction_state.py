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
        SET
          extraction_status = 'provisional',
          provisional_extraction = jsonb_build_object(
            'status', 'provisional',
            'captured_at', NOW(),
            'summary', COALESCE(NULLIF(BTRIM(event_summary), ''), canonical_summary),
            'extracted_who', to_jsonb(extracted_who),
            'extracted_what', to_jsonb(extracted_what),
            'extracted_where', to_jsonb(extracted_where),
            'extracted_when', to_jsonb(extracted_when),
            'extracted_claims', to_jsonb(extracted_claims),
            'categories', COALESCE(to_jsonb(categories), '[]'::jsonb),
            'has_contradictions', to_jsonb(has_contradictions),
            'contradiction_notes', to_jsonb(contradiction_notes),
            'provenance', extraction_provenance,
            'replay_enqueued', 'true'::jsonb,
            'policy', extracted_claims -> '_llm_policy'
          ),
          event_summary = NULL,
          extracted_who = NULL,
          extracted_what = NULL,
          extracted_where = NULL,
          extracted_when = NULL,
          extracted_claims = NULL,
          categories = ARRAY[]::text[],
          has_contradictions = false,
          contradiction_notes = NULL
        WHERE COALESCE(extracted_claims -> '_llm_policy' ->> 'degraded_llm', 'false') = 'true'
        """
    )
    # Preserve legacy claim rows during backfill: pre-split degraded rows do not retain
    # enough information to distinguish "no canonical claims existed" from "canonical
    # claim identity only survives in event_claims until replay repairs the event".
    op.execute(
        """
        INSERT INTO llm_replay_queue (
          id,
          stage,
          event_id,
          priority,
          status,
          attempt_count,
          last_attempt_at,
          locked_at,
          locked_by,
          processed_at,
          last_error,
          details
        )
        SELECT
          gen_random_uuid(),
          'tier2',
          id,
          500,
          'pending',
          0,
          NULL,
          NULL,
          NULL,
          NULL,
          NULL,
          jsonb_build_object(
            'reason', 'migration_backfill_degraded_llm',
            'migration', '0033_event_provisional_state',
            'original_extraction_provenance', provisional_extraction -> 'provenance'
          )
        FROM events
        WHERE extraction_status = 'provisional'
          AND COALESCE(
            provisional_extraction -> 'policy' ->> 'degraded_llm',
            'false'
          ) = 'true'
        ON CONFLICT (stage, event_id) DO UPDATE
        SET
          priority = EXCLUDED.priority,
          status = 'pending',
          attempt_count = 0,
          last_attempt_at = NULL,
          locked_at = NULL,
          locked_by = NULL,
          processed_at = NULL,
          last_error = NULL,
          details = EXCLUDED.details
        WHERE llm_replay_queue.status != 'processing'
        """
    )
    op.execute(
        """
        UPDATE events
        SET extraction_status = 'canonical'
        WHERE extraction_status = 'none'
          AND COALESCE(extraction_provenance ->> 'status', '') != 'replay_pending'
          AND (
            COALESCE(NULLIF(BTRIM(event_summary), ''), '') != ''
            AND COALESCE(NULLIF(BTRIM(event_summary), ''), '') !=
              COALESCE(NULLIF(BTRIM(canonical_summary), ''), '')
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
