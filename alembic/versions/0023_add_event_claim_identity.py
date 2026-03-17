"""Add stable event-claim identity for trend evidence.

Revision ID: 0023_event_claim_identity
Revises: 0022_evidence_active_unique
Create Date: 2026-03-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0023_event_claim_identity"
down_revision = "0022_evidence_active_unique"
branch_labels = None
depends_on = None

_FALLBACK_CLAIM_KEY = "__event__"


def upgrade() -> None:
    op.create_table(
        "event_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_key", sa.String(length=255), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=20), nullable=False, server_default="statement"),
        sa.Column("claim_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "claim_type IN ('fallback', 'statement')",
            name="check_event_claims_claim_type_allowed",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "claim_key", name="uq_event_claims_event_claim_key"),
        sa.UniqueConstraint("event_id", "id", name="uq_event_claims_event_id_id"),
    )
    op.create_index(
        "idx_event_claims_event_active",
        "event_claims",
        ["event_id", "is_active"],
    )

    op.add_column(
        "trend_evidence",
        sa.Column("event_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO event_claims (
                id,
                event_id,
                claim_key,
                claim_text,
                claim_type,
                claim_order,
                is_active,
                first_seen_at,
                last_seen_at,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                events.id,
                :claim_key,
                COALESCE(
                    NULLIF(BTRIM(events.extracted_what), ''),
                    NULLIF(BTRIM(events.canonical_summary), ''),
                    'Cluster event'
                ),
                'fallback',
                0,
                true,
                COALESCE(events.first_seen_at, now()),
                COALESCE(events.last_mention_at, events.first_seen_at, now()),
                now(),
                now()
            FROM events
            """
        ).bindparams(claim_key=_FALLBACK_CLAIM_KEY)
    )
    op.execute(
        sa.text(
            """
            UPDATE trend_evidence
            SET event_claim_id = event_claims.id
            FROM event_claims
            WHERE trend_evidence.event_id = event_claims.event_id
              AND event_claims.claim_key = :claim_key
            """
        ).bindparams(claim_key=_FALLBACK_CLAIM_KEY)
    )
    op.alter_column("trend_evidence", "event_claim_id", nullable=False)
    op.create_foreign_key(
        "fk_trend_evidence_event_claim_id_event_claims",
        "trend_evidence",
        "event_claims",
        ["event_claim_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_trend_evidence_event_id_event_claim_id_event_claims",
        "trend_evidence",
        "event_claims",
        ["event_id", "event_claim_id"],
        ["event_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_evidence_event_claim", "trend_evidence", ["event_claim_id"])
    op.drop_index("uq_trend_event_signal_active", table_name="trend_evidence")
    op.create_index(
        "uq_trend_event_claim_signal_active",
        "trend_evidence",
        ["trend_id", "event_claim_id", "signal_type"],
        unique=True,
        postgresql_where=sa.text("is_invalidated = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_trend_event_claim_signal_active", table_name="trend_evidence")
    op.drop_index("idx_evidence_event_claim", table_name="trend_evidence")
    op.drop_constraint(
        "fk_trend_evidence_event_id_event_claim_id_event_claims",
        "trend_evidence",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_trend_evidence_event_claim_id_event_claims",
        "trend_evidence",
        type_="foreignkey",
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY trend_id, event_id, signal_type
                        ORDER BY is_invalidated ASC, created_at DESC, id DESC
                    ) AS row_num
                FROM trend_evidence
            )
            DELETE FROM trend_evidence
            USING ranked
            WHERE trend_evidence.id = ranked.id
              AND ranked.row_num > 1
            """
        )
    )
    op.create_index(
        "uq_trend_event_signal_active",
        "trend_evidence",
        ["trend_id", "event_id", "signal_type"],
        unique=True,
        postgresql_where=sa.text("is_invalidated = false"),
    )
    op.drop_column("trend_evidence", "event_claim_id")
    op.drop_index("idx_event_claims_event_active", table_name="event_claims")
    op.drop_table("event_claims")
