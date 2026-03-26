"""Add canonical entity registry and event entity links.

Revision ID: 0038_canonical_entity_registry
Revises: 0037_add_event_adjudications
Create Date: 2026-03-26 21:55:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0038_canonical_entity_registry"
down_revision = "0037_add_event_adjudications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column(
            "entity_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_auto_seeded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "entity_type IN ('person', 'organization', 'location')",
            name="check_canonical_entities_type_allowed",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "normalized_name",
            name="uq_canonical_entities_type_normalized_name",
        ),
    )
    op.create_index(
        "idx_canonical_entities_type_name",
        "canonical_entities",
        ["entity_type", "normalized_name"],
        unique=False,
    )

    op.create_table(
        "canonical_entity_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["canonical_entity_id"],
            ["canonical_entities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_entity_id",
            "normalized_alias",
            name="uq_canonical_entity_aliases_entity_alias",
        ),
    )
    op.create_index(
        "idx_canonical_entity_aliases_normalized_alias",
        "canonical_entity_aliases",
        ["normalized_alias"],
        unique=False,
    )

    op.create_table(
        "event_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_role", sa.String(length=20), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("mention_text", sa.Text(), nullable=False),
        sa.Column("mention_normalized", sa.String(length=255), nullable=False),
        sa.Column("canonical_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_status", sa.String(length=20), nullable=False),
        sa.Column("resolution_reason", sa.String(length=40), nullable=True),
        sa.Column(
            "resolution_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "entity_role IN ('actor', 'location')",
            name="check_event_entities_role_allowed",
        ),
        sa.CheckConstraint(
            "entity_type IN ('person', 'organization', 'location')",
            name="check_event_entities_type_allowed",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('resolved', 'ambiguous', 'unresolved')",
            name="check_event_entities_resolution_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_entity_id"], ["canonical_entities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "entity_role",
            "entity_type",
            "mention_normalized",
            name="uq_event_entities_event_mention",
        ),
    )
    op.create_index(
        "idx_event_entities_event_role",
        "event_entities",
        ["event_id", "entity_role"],
        unique=False,
    )
    op.create_index(
        "idx_event_entities_canonical_entity",
        "event_entities",
        ["canonical_entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_event_entities_canonical_entity", table_name="event_entities")
    op.drop_index("idx_event_entities_event_role", table_name="event_entities")
    op.drop_table("event_entities")
    op.drop_index(
        "idx_canonical_entity_aliases_normalized_alias",
        table_name="canonical_entity_aliases",
    )
    op.drop_table("canonical_entity_aliases")
    op.drop_index("idx_canonical_entities_type_name", table_name="canonical_entities")
    op.drop_table("canonical_entities")
