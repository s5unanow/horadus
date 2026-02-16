from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.embedding_lineage import build_embedding_lineage_report

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_build_embedding_lineage_report_aggregates_counts(mock_db_session) -> None:
    mock_db_session.scalar.side_effect = [
        5,  # raw vectors
        2,  # raw rows_without_vector
        3,  # raw target_model_vectors
        1,  # raw vectors_missing_model
        4,  # event vectors
        1,  # event rows_without_vector
        4,  # event target_model_vectors
        0,  # event vectors_missing_model
    ]
    mock_db_session.execute.side_effect = [
        SimpleNamespace(
            all=lambda: [
                ("text-embedding-3-small", 3),
                ("text-embedding-ada-002", 1),
            ]
        ),
        SimpleNamespace(all=lambda: [("text-embedding-3-small", 4)]),
    ]

    report = await build_embedding_lineage_report(
        mock_db_session,
        target_model="text-embedding-3-small",
    )

    assert report.target_model == "text-embedding-3-small"
    assert report.raw_items.vectors == 5
    assert report.raw_items.target_model_vectors == 3
    assert report.raw_items.vectors_missing_model == 1
    assert report.raw_items.vectors_other_models == 1
    assert report.raw_items.reembed_scope == 2
    assert report.raw_items.has_mixed_models is True
    assert report.events.vectors == 4
    assert report.events.reembed_scope == 0
    assert report.total_vectors == 9
    assert report.total_reembed_scope == 2
    assert report.has_mixed_populations is True


@pytest.mark.asyncio
async def test_build_embedding_lineage_report_rejects_blank_target_model(mock_db_session) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        await build_embedding_lineage_report(mock_db_session, target_model="   ")
