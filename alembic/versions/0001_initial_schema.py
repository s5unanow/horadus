"""Initial database schema.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-02-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions (idempotent; required by schema)
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Enums
    source_type_enum = postgresql.ENUM(
        "rss",
        "telegram",
        "gdelt",
        "api",
        "scraper",
        name="source_type",
    )
    processing_status_enum = postgresql.ENUM(
        "pending",
        "processing",
        "classified",
        "noise",
        "error",
        name="processing_status",
    )
    source_type_enum.create(op.get_bind(), checkfirst=True)
    processing_status_enum.create(op.get_bind(), checkfirst=True)

    # ---------------------------------------------------------------------
    # Core tables
    # ---------------------------------------------------------------------
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("type", source_type_enum, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("credibility_score", sa.Numeric(3, 2), nullable=False),
        sa.Column("source_tier", sa.String(length=20), nullable=False),
        sa.Column("reporting_type", sa.String(length=20), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "credibility_score >= 0 AND credibility_score <= 1",
            name="check_credibility_range",
        ),
    )
    op.create_index("idx_sources_active", "sources", ["is_active"])
    op.create_index("idx_sources_type", "sources", ["type"])
    op.create_index("idx_sources_tier", "sources", ["source_tier"])

    op.create_table(
        "raw_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=2048), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("processing_status", processing_status_enum, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_external"),
    )
    op.create_index("idx_raw_items_status", "raw_items", ["processing_status"])
    op.create_index("idx_raw_items_hash", "raw_items", ["content_hash"])
    op.create_index("idx_raw_items_fetched", "raw_items", ["fetched_at"])
    op.create_index("idx_raw_items_source_fetched", "raw_items", ["source_id", "fetched_at"])

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("canonical_summary", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("extracted_who", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("extracted_what", sa.Text(), nullable=True),
        sa.Column("extracted_where", sa.String(length=255), nullable=True),
        sa.Column("extracted_when", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_claims", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("categories", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("unique_source_count", sa.Integer(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_mention_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "primary_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("has_contradictions", sa.Boolean(), nullable=False),
        sa.Column("contradiction_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_events_first_seen", "events", ["first_seen_at"])
    op.create_index(
        "idx_events_categories",
        "events",
        ["categories"],
        postgresql_using="gin",
    )
    op.create_index("idx_events_lifecycle", "events", ["lifecycle_status", "last_mention_at"])

    op.create_table(
        "event_items",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_items.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "trends",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("baseline_log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("current_log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("indicators", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decay_half_life_days", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_trends_name"),
    )
    op.create_index("idx_trends_active", "trends", ["is_active"])

    op.create_table(
        "trend_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "trend_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trends.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_type", sa.String(length=100), nullable=False),
        sa.Column("credibility_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("corroboration_factor", sa.Numeric(5, 2), nullable=True),
        sa.Column("novelty_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("severity_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("delta_log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("trend_id", "event_id", "signal_type", name="uq_trend_event_signal"),
    )
    op.create_index("idx_evidence_event", "trend_evidence", ["event_id"])
    op.create_index("idx_evidence_trend_created", "trend_evidence", ["trend_id", "created_at"])

    op.create_table(
        "trend_snapshots",
        sa.Column(
            "trend_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trends.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("log_odds", sa.Numeric(10, 6), nullable=False),
        sa.Column("event_count_24h", sa.Integer(), nullable=True),
    )

    # Convert to Timescale hypertable (idempotent).
    op.execute(
        "SELECT create_hypertable('trend_snapshots', 'timestamp', if_not_exists => TRUE);"
    )

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "trend_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trends.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("statistics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("top_events", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_reports_trend", "reports", ["trend_id"])
    op.create_index("idx_reports_type_period", "reports", ["report_type", "period_end"])

    op.create_table(
        "trend_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "trend_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trends.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prediction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_probability", sa.Numeric(5, 4), nullable=False),
        sa.Column("predicted_risk_level", sa.String(length=20), nullable=False),
        sa.Column("probability_band_low", sa.Numeric(5, 4), nullable=False),
        sa.Column("probability_band_high", sa.Numeric(5, 4), nullable=False),
        sa.Column("outcome_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("outcome_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("brier_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("recorded_by", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_outcomes_outcome", "trend_outcomes", ["outcome"])
    op.create_index("idx_outcomes_trend_date", "trend_outcomes", ["trend_id", "prediction_date"])

    op.create_table(
        "human_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("original_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("corrected_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_feedback_action", "human_feedback", ["action"])
    op.create_index("idx_feedback_target", "human_feedback", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("idx_feedback_target", table_name="human_feedback")
    op.drop_index("idx_feedback_action", table_name="human_feedback")
    op.drop_table("human_feedback")

    op.drop_index("idx_outcomes_trend_date", table_name="trend_outcomes")
    op.drop_index("idx_outcomes_outcome", table_name="trend_outcomes")
    op.drop_table("trend_outcomes")

    op.drop_index("idx_reports_type_period", table_name="reports")
    op.drop_index("idx_reports_trend", table_name="reports")
    op.drop_table("reports")

    op.drop_table("trend_snapshots")

    op.drop_index("idx_evidence_trend_created", table_name="trend_evidence")
    op.drop_index("idx_evidence_event", table_name="trend_evidence")
    op.drop_table("trend_evidence")

    op.drop_index("idx_trends_active", table_name="trends")
    op.drop_table("trends")

    op.drop_table("event_items")

    op.drop_index("idx_events_lifecycle", table_name="events")
    op.drop_index("idx_events_categories", table_name="events")
    op.drop_index("idx_events_first_seen", table_name="events")
    op.drop_table("events")

    op.drop_index("idx_raw_items_source_fetched", table_name="raw_items")
    op.drop_index("idx_raw_items_fetched", table_name="raw_items")
    op.drop_index("idx_raw_items_hash", table_name="raw_items")
    op.drop_index("idx_raw_items_status", table_name="raw_items")
    op.drop_table("raw_items")

    op.drop_index("idx_sources_tier", table_name="sources")
    op.drop_index("idx_sources_type", table_name="sources")
    op.drop_index("idx_sources_active", table_name="sources")
    op.drop_table("sources")

    # Enums
    processing_status_enum = postgresql.ENUM(name="processing_status")
    source_type_enum = postgresql.ENUM(name="source_type")
    processing_status_enum.drop(op.get_bind(), checkfirst=True)
    source_type_enum.drop(op.get_bind(), checkfirst=True)
