"""Harden active evidence uniqueness for null state versions.

Revision ID: 0039_evidence_null_state_unique
Revises: 0038_canonical_entity_registry
Create Date: 2026-07-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0039_evidence_null_state_unique"
down_revision = "0038_canonical_entity_registry"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_trend_event_claim_signal_active"


def _assert_no_duplicate_active_null_state_evidence() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT trend_id, event_claim_id, signal_type
            FROM trend_evidence
            WHERE state_version_id IS NULL
              AND is_invalidated = false
            GROUP BY trend_id, event_claim_id, signal_type
            HAVING COUNT(*) > 1
            LIMIT 1
            """
            )
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce active evidence uniqueness: duplicate null-state "
            "trend evidence requires operator reconciliation"
        )


def upgrade() -> None:
    _assert_no_duplicate_active_null_state_evidence()
    op.drop_index(INDEX_NAME, table_name="trend_evidence")
    op.create_index(
        INDEX_NAME,
        "trend_evidence",
        ["trend_id", "state_version_id", "event_claim_id", "signal_type"],
        unique=True,
        postgresql_where=sa.text("is_invalidated = false"),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="trend_evidence")
    op.create_index(
        INDEX_NAME,
        "trend_evidence",
        ["state_version_id", "event_claim_id", "signal_type"],
        unique=True,
        postgresql_where=sa.text("is_invalidated = false"),
    )
