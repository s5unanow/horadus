from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from src.storage.models import (
    ApiUsage,
    Event,
    EventClaim,
    EventItem,
    EventLineage,
    RawItem,
    Report,
    Source,
    TrendDefinitionVersion,
    TrendEvidence,
    TrendRestatement,
)

pytestmark = pytest.mark.unit


def _render_default(column_name: str) -> str:
    column = ApiUsage.__table__.c[column_name]
    server_default = column.server_default
    assert server_default is not None
    return str(
        server_default.arg.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_api_usage_server_defaults_match_migration_baseline() -> None:
    assert "gen_random_uuid" in _render_default("id").lower()
    assert _render_default("call_count") == "0"
    assert _render_default("input_tokens") == "0"
    assert _render_default("output_tokens") == "0"
    assert _render_default("estimated_cost_usd") == "0"


def test_pgvector_indexes_present_in_model_metadata() -> None:
    raw_item_indexes = {index.name for index in RawItem.__table__.indexes}
    event_indexes = {index.name for index in Event.__table__.indexes}

    assert "idx_raw_items_embedding" in raw_item_indexes
    assert "idx_events_embedding" in event_indexes


def test_pgvector_indexes_match_migration_profile_lists_setting() -> None:
    raw_item_index = next(
        index for index in RawItem.__table__.indexes if index.name == "idx_raw_items_embedding"
    )
    event_index = next(
        index for index in Event.__table__.indexes if index.name == "idx_events_embedding"
    )

    assert raw_item_index.dialect_options["postgresql"]["with"] == {"lists": 64}
    assert event_index.dialect_options["postgresql"]["with"] == {"lists": 64}


def test_embedding_lineage_columns_present_in_model_metadata() -> None:
    assert "embedding_model" in RawItem.__table__.c
    assert "embedding_generated_at" in RawItem.__table__.c
    assert "embedding_input_tokens" in RawItem.__table__.c
    assert "embedding_retained_tokens" in RawItem.__table__.c
    assert "embedding_was_truncated" in RawItem.__table__.c
    assert "embedding_truncation_strategy" in RawItem.__table__.c
    assert "embedding_model" in Event.__table__.c
    assert "embedding_generated_at" in Event.__table__.c
    assert "embedding_input_tokens" in Event.__table__.c
    assert "embedding_retained_tokens" in Event.__table__.c
    assert "embedding_was_truncated" in Event.__table__.c
    assert "embedding_truncation_strategy" in Event.__table__.c


def test_report_grounding_columns_present_in_model_metadata() -> None:
    assert "grounding_status" in Report.__table__.c
    assert "grounding_violation_count" in Report.__table__.c
    assert "grounding_references" in Report.__table__.c
    assert "generation_manifest" in Report.__table__.c


def test_source_ingestion_watermark_column_present_in_model_metadata() -> None:
    assert "ingestion_window_end_at" in Source.__table__.c
    assert any(
        index.name == "idx_sources_ingestion_window_end_at" for index in Source.__table__.indexes
    )


def test_event_items_item_uniqueness_constraint_present_in_model_metadata() -> None:
    unique_constraint_names = {
        constraint.name
        for constraint in EventItem.__table__.constraints
        if getattr(constraint, "name", None)
    }
    assert "uq_event_items_item_id" in unique_constraint_names


def test_trend_definition_version_indexes_present_in_model_metadata() -> None:
    index_names = {index.name for index in TrendDefinitionVersion.__table__.indexes}
    assert "idx_trend_definition_versions_trend_recorded" in index_names
    assert "idx_trend_definition_versions_hash" in index_names


def test_dimension_check_constraints_present_in_model_metadata() -> None:
    source_constraint_names = {
        constraint.name
        for constraint in Source.__table__.constraints
        if getattr(constraint, "name", None)
    }
    event_constraint_names = {
        constraint.name
        for constraint in Event.__table__.constraints
        if getattr(constraint, "name", None)
    }

    assert "check_sources_source_tier_allowed" in source_constraint_names
    assert "check_sources_reporting_type_allowed" in source_constraint_names
    assert "check_events_lifecycle_status_allowed" in event_constraint_names
    assert "check_events_epistemic_state_allowed" in event_constraint_names
    assert "check_events_activity_state_allowed" in event_constraint_names
    assert "epistemic_state" in Event.__table__.c
    assert "activity_state" in Event.__table__.c
    assert "independent_evidence_count" in Event.__table__.c
    assert "corroboration_score" in Event.__table__.c
    assert "corroboration_mode" in Event.__table__.c
    assert "provenance_summary" in Event.__table__.c
    assert "extraction_provenance" in Event.__table__.c
    assert "idx_events_activity" in {index.name for index in Event.__table__.indexes}


def test_trend_evidence_factorization_columns_present_in_model_metadata() -> None:
    assert "base_weight" in TrendEvidence.__table__.c
    assert "direction_multiplier" in TrendEvidence.__table__.c
    assert "trend_definition_hash" in TrendEvidence.__table__.c
    assert "scoring_math_version" in TrendEvidence.__table__.c
    assert "scoring_parameter_set" in TrendEvidence.__table__.c
    assert "event_claim_id" in TrendEvidence.__table__.c


def test_event_claim_constraints_present_in_model_metadata() -> None:
    constraint_names = {
        constraint.name
        for constraint in EventClaim.__table__.constraints
        if getattr(constraint, "name", None)
    }

    assert "check_event_claims_claim_type_allowed" in constraint_names
    assert "uq_event_claims_event_claim_key" in constraint_names
    assert "uq_event_claims_event_id_id" in constraint_names


def test_trend_evidence_claim_consistency_constraint_present_in_model_metadata() -> None:
    constraint_names = {
        constraint.name
        for constraint in TrendEvidence.__table__.constraints
        if getattr(constraint, "name", None)
    }

    assert "fk_trend_evidence_event_id_event_claim_id_event_claims" in constraint_names


def test_trend_evidence_active_unique_index_present_in_model_metadata() -> None:
    evidence_index = next(
        index
        for index in TrendEvidence.__table__.indexes
        if index.name == "uq_trend_event_claim_signal_active"
    )
    where_clause = evidence_index.dialect_options["postgresql"]["where"]

    assert evidence_index.unique is True
    assert (
        str(
            where_clause.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        == "is_invalidated = false"
    )


def test_trend_restatement_columns_and_constraints_present_in_model_metadata() -> None:
    constraint_names = {
        constraint.name
        for constraint in TrendRestatement.__table__.constraints
        if getattr(constraint, "name", None)
    }
    index_names = {index.name for index in TrendRestatement.__table__.indexes}

    assert "trend_evidence_id" in TrendRestatement.__table__.c
    assert "compensation_delta_log_odds" in TrendRestatement.__table__.c
    assert "scoring_math_version" in TrendRestatement.__table__.c
    assert "scoring_parameter_set" in TrendRestatement.__table__.c
    assert "check_trend_restatements_kind_allowed" in constraint_names
    assert "check_trend_restatements_source_allowed" in constraint_names
    assert "idx_trend_restatements_trend_recorded" in index_names


def test_event_lineage_columns_and_constraints_present_in_model_metadata() -> None:
    constraint_names = {
        constraint.name
        for constraint in EventLineage.__table__.constraints
        if getattr(constraint, "name", None)
    }
    index_names = {index.name for index in EventLineage.__table__.indexes}

    assert "lineage_kind" in EventLineage.__table__.c
    assert "details" in EventLineage.__table__.c
    assert "check_event_lineage_kind_allowed" in constraint_names
    assert "idx_event_lineage_source_created" in index_names
    assert "idx_event_lineage_target_created" in index_names


def test_restatement_models_module_imports_without_circular_dependency() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; importlib.import_module('src.storage.restatement_models')",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_event_lineage_models_module_imports_without_circular_dependency() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; importlib.import_module('src.storage.event_lineage_models')",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
