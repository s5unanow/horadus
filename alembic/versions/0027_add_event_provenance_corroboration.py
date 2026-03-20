"""Add event-level provenance-aware corroboration fields.

Revision ID: 0027_event_provenance
Revises: 0026_split_event_state_axes
Create Date: 2026-03-20 17:10:00.000000
"""

from __future__ import annotations

from collections import defaultdict
import json

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from src.processing.corroboration_provenance import (
    EventSourceProvenance,
    fallback_event_provenance_summary,
    summarize_event_provenance,
)

# revision identifiers, used by Alembic.
revision = "0027_event_provenance"
down_revision = "0026_split_event_state_axes"
branch_labels = None
depends_on = None


def _backfill_event_provenance(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                e.id AS event_id,
                e.source_count AS source_count,
                e.unique_source_count AS unique_source_count,
                s.id AS source_id,
                s.name AS source_name,
                s.url AS source_url,
                s.source_tier AS source_tier,
                s.reporting_type AS reporting_type,
                ri.url AS item_url,
                ri.title AS title,
                ri.author AS author,
                ri.content_hash AS content_hash
            FROM events AS e
            LEFT JOIN event_items AS ei ON ei.event_id = e.id
            LEFT JOIN raw_items AS ri ON ri.id = ei.item_id
            LEFT JOIN sources AS s ON s.id = ri.source_id
            ORDER BY e.id, ei.added_at
            """
        )
    ).mappings()
    by_event: dict[object, dict[str, object]] = defaultdict(
        lambda: {"source_count": 0, "unique_source_count": 0, "observations": []}
    )
    for row in rows:
        payload = by_event[row["event_id"]]
        payload["source_count"] = int(row["source_count"] or 0)
        payload["unique_source_count"] = int(row["unique_source_count"] or 0)
        if row["source_id"] is not None:
            observations = payload["observations"]
            assert isinstance(observations, list)
            observations.append(
                EventSourceProvenance(
                    source_id=row["source_id"],
                    source_name=row["source_name"],
                    source_url=row["source_url"],
                    source_tier=row["source_tier"],
                    reporting_type=row["reporting_type"],
                    item_url=row["item_url"],
                    title=row["title"],
                    author=row["author"],
                    content_hash=row["content_hash"],
                )
            )

    update_stmt = sa.text(
        """
        UPDATE events
        SET independent_evidence_count = :independent_evidence_count,
            corroboration_score = :corroboration_score,
            corroboration_mode = :corroboration_mode,
            provenance_summary = CAST(:provenance_summary AS jsonb)
        WHERE id = :event_id
        """
    )
    for event_id, payload in by_event.items():
        observations = payload["observations"]
        assert isinstance(observations, list)
        source_count = int(payload["source_count"])
        unique_source_count = int(payload["unique_source_count"])
        summary = summarize_event_provenance(
            observations=observations,
            raw_source_count=source_count,
            unique_source_count=unique_source_count,
        )
        if not observations:
            summary = fallback_event_provenance_summary(
                raw_source_count=source_count,
                unique_source_count=unique_source_count,
                reason="migration_backfill_no_event_items",
            )
        connection.execute(
            update_stmt,
            {
                "event_id": event_id,
                "independent_evidence_count": summary.independent_evidence_count,
                "corroboration_score": summary.weighted_corroboration_score,
                "corroboration_mode": summary.method,
                "provenance_summary": json.dumps(summary.as_dict()),
            },
        )


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "independent_evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "corroboration_score",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="1.00",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "corroboration_mode",
            sa.String(length=20),
            nullable=False,
            server_default="fallback",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "provenance_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    _backfill_event_provenance(op.get_bind())
    op.alter_column("events", "independent_evidence_count", server_default=None)
    op.alter_column("events", "corroboration_score", server_default=None)
    op.alter_column("events", "corroboration_mode", server_default=None)
    op.alter_column("events", "provenance_summary", server_default=None)


def downgrade() -> None:
    op.drop_column("events", "provenance_summary")
    op.drop_column("events", "corroboration_mode")
    op.drop_column("events", "corroboration_score")
    op.drop_column("events", "independent_evidence_count")
