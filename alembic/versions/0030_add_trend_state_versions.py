"""Add versioned live trend state references.

Revision ID: 0030_trend_state_versions
Revises: 0029_event_lineage
Create Date: 2026-03-22
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0030_trend_state_versions"
down_revision = "0029_event_lineage"
branch_labels = None
depends_on = None

SCORING_MATH_VERSION = "trend-scoring-v1"
SCORING_PARAMETER_SET = "stable-default-v1"


def _definition_hash(definition: object) -> str:
    normalized = definition if isinstance(definition, dict) else {}
    serialized = json.dumps(
        normalized,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.create_table(
        "trend_state_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trend_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_state_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("definition_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("definition_hash", sa.String(length=64), nullable=True),
        sa.Column("activation_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "scoring_math_version",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text(f"'{SCORING_MATH_VERSION}'"),
        ),
        sa.Column(
            "scoring_parameter_set",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text(f"'{SCORING_PARAMETER_SET}'"),
        ),
        sa.Column("baseline_log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("starting_log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("current_log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("decay_half_life_days", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("context", sa.String(length=255), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "activation_kind IN ('create', 'rebase', 'replay', 'new_line')",
            name="check_trend_state_versions_activation_kind_allowed",
        ),
        sa.ForeignKeyConstraint(["trend_id"], ["trends.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_state_version_id"],
            ["trend_state_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["definition_version_id"],
            ["trend_definition_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_trend_state_versions_trend_activated",
        "trend_state_versions",
        ["trend_id", "activated_at"],
        unique=False,
    )
    op.create_index(
        "idx_trend_state_versions_definition",
        "trend_state_versions",
        ["definition_version_id"],
        unique=False,
    )

    op.add_column(
        "trends",
        sa.Column("active_definition_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("trends", sa.Column("active_definition_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "trends",
        sa.Column("active_scoring_math_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "trends",
        sa.Column("active_scoring_parameter_set", sa.String(length=64), nullable=True),
    )
    op.add_column("trends", sa.Column("active_state_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_trends_active_definition_version",
        "trends",
        "trend_definition_versions",
        ["active_definition_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_trends_active_state_version",
        "trends",
        "trend_state_versions",
        ["active_state_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "trend_evidence",
        sa.Column("state_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_trend_evidence_state_version",
        "trend_evidence",
        "trend_state_versions",
        ["state_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_evidence_state_created",
        "trend_evidence",
        ["state_version_id", "created_at"],
        unique=False,
    )

    op.add_column(
        "trend_restatements",
        sa.Column("state_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_trend_restatements_state_version",
        "trend_restatements",
        "trend_state_versions",
        ["state_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_trend_restatements_state_recorded",
        "trend_restatements",
        ["state_version_id", "recorded_at"],
        unique=False,
    )

    op.add_column(
        "trend_snapshots",
        sa.Column("state_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_trend_snapshots_state_version",
        "trend_snapshots",
        "trend_state_versions",
        ["state_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    trends = bind.execute(
        sa.text(
            """
            SELECT id, definition, baseline_log_odds, current_log_odds,
                   decay_half_life_days, updated_at
            FROM trends
            """
        )
    ).mappings()
    for trend in trends:
        trend_id = trend["id"]
        definition_row = bind.execute(
            sa.text(
                """
                SELECT id, definition_hash
                FROM trend_definition_versions
                WHERE trend_id = :trend_id
                ORDER BY recorded_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"trend_id": trend_id},
        ).mappings().first()
        if definition_row is None:
            definition_id = uuid4()
            definition_hash = _definition_hash(trend["definition"])
            bind.execute(
                sa.text(
                    """
                    INSERT INTO trend_definition_versions (
                        id, trend_id, definition_hash, definition, actor, context, recorded_at
                    ) VALUES (
                        :id, :trend_id, :definition_hash, CAST(:definition AS jsonb),
                        'migration', '0030_backfill_active_state', :recorded_at
                    )
                    """
                ),
                {
                    "id": definition_id,
                    "trend_id": trend_id,
                    "definition_hash": definition_hash,
                    "definition": json.dumps(trend["definition"] or {}),
                    "recorded_at": trend["updated_at"] or datetime.now(UTC),
                },
            )
        else:
            definition_id = definition_row["id"]
            definition_hash = definition_row["definition_hash"]

        state_id = uuid4()
        activated_at = trend["updated_at"] or datetime.now(UTC)
        bind.execute(
            sa.text(
                """
                INSERT INTO trend_state_versions (
                    id, trend_id, parent_state_version_id, definition_version_id, definition_hash,
                    activation_kind, scoring_math_version, scoring_parameter_set,
                    baseline_log_odds, starting_log_odds, current_log_odds,
                    decay_half_life_days, actor, context, details, activated_at
                ) VALUES (
                    :id, :trend_id, NULL, :definition_version_id, :definition_hash,
                    'create', :scoring_math_version, :scoring_parameter_set,
                    :baseline_log_odds, :starting_log_odds, :current_log_odds,
                    :decay_half_life_days, 'migration', '0030_backfill_active_state',
                    CAST(:details AS jsonb), :activated_at
                )
                """
            ),
            {
                "id": state_id,
                "trend_id": trend_id,
                "definition_version_id": definition_id,
                "definition_hash": definition_hash,
                "scoring_math_version": SCORING_MATH_VERSION,
                "scoring_parameter_set": SCORING_PARAMETER_SET,
                "baseline_log_odds": trend["baseline_log_odds"],
                "starting_log_odds": trend["current_log_odds"],
                "current_log_odds": trend["current_log_odds"],
                "decay_half_life_days": trend["decay_half_life_days"],
                "details": json.dumps({"backfilled": True}),
                "activated_at": activated_at,
            },
        )
        bind.execute(
            sa.text(
                """
                UPDATE trends
                SET active_definition_version_id = :definition_version_id,
                    active_definition_hash = :definition_hash,
                    active_scoring_math_version = :scoring_math_version,
                    active_scoring_parameter_set = :scoring_parameter_set,
                    active_state_version_id = :state_id
                WHERE id = :trend_id
                """
            ),
            {
                "trend_id": trend_id,
                "definition_version_id": definition_id,
                "definition_hash": definition_hash,
                "scoring_math_version": SCORING_MATH_VERSION,
                "scoring_parameter_set": SCORING_PARAMETER_SET,
                "state_id": state_id,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE trend_evidence SET state_version_id = :state_id "
                "WHERE trend_id = :trend_id AND state_version_id IS NULL"
            ),
            {"state_id": state_id, "trend_id": trend_id},
        )
        bind.execute(
            sa.text(
                "UPDATE trend_restatements SET state_version_id = :state_id "
                "WHERE trend_id = :trend_id AND state_version_id IS NULL"
            ),
            {"state_id": state_id, "trend_id": trend_id},
        )
        bind.execute(
            sa.text(
                "UPDATE trend_snapshots SET state_version_id = :state_id "
                "WHERE trend_id = :trend_id AND state_version_id IS NULL"
            ),
            {"state_id": state_id, "trend_id": trend_id},
        )

    op.drop_index("uq_trend_event_claim_signal_active", table_name="trend_evidence")
    op.create_index(
        "uq_trend_event_claim_signal_active",
        "trend_evidence",
        ["state_version_id", "event_claim_id", "signal_type"],
        unique=True,
        postgresql_where=sa.text("is_invalidated = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_trend_event_claim_signal_active", table_name="trend_evidence")
    op.create_index(
        "uq_trend_event_claim_signal_active",
        "trend_evidence",
        ["trend_id", "event_claim_id", "signal_type"],
        unique=True,
        postgresql_where=sa.text("is_invalidated = false"),
    )
    op.drop_constraint("fk_trend_snapshots_state_version", "trend_snapshots", type_="foreignkey")
    op.drop_column("trend_snapshots", "state_version_id")

    op.drop_index("idx_trend_restatements_state_recorded", table_name="trend_restatements")
    op.drop_constraint(
        "fk_trend_restatements_state_version",
        "trend_restatements",
        type_="foreignkey",
    )
    op.drop_column("trend_restatements", "state_version_id")

    op.drop_index("idx_evidence_state_created", table_name="trend_evidence")
    op.drop_constraint("fk_trend_evidence_state_version", "trend_evidence", type_="foreignkey")
    op.drop_column("trend_evidence", "state_version_id")

    op.drop_constraint("fk_trends_active_state_version", "trends", type_="foreignkey")
    op.drop_constraint("fk_trends_active_definition_version", "trends", type_="foreignkey")
    op.drop_column("trends", "active_state_version_id")
    op.drop_column("trends", "active_scoring_parameter_set")
    op.drop_column("trends", "active_scoring_math_version")
    op.drop_column("trends", "active_definition_hash")
    op.drop_column("trends", "active_definition_version_id")

    op.drop_index("idx_trend_state_versions_definition", table_name="trend_state_versions")
    op.drop_index(
        "idx_trend_state_versions_trend_activated",
        table_name="trend_state_versions",
    )
    op.drop_table("trend_state_versions")
