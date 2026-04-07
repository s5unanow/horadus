"""Runtime-facing helpers for embedding-lineage reporting."""

from __future__ import annotations

from typing import Any

from src.core import embedding_lineage as embedding_lineage_module


def format_embedding_model_counts(summary: Any) -> str:
    """Render one embedding-lineage model-count summary line."""

    if not summary.model_counts:
        return "none"
    return ", ".join(f"{entry.model}={entry.count}" for entry in summary.model_counts)


async def collect_embedding_lineage_runtime(
    *,
    target_model: str,
    fail_on_mixed: bool,
) -> tuple[dict[str, Any], list[str], int]:
    """Collect embedding-lineage data in the CLI runtime payload shape."""

    from src.storage import database as database_module

    async with database_module.async_session_maker() as session:
        report = await embedding_lineage_module.build_embedding_lineage_report(
            session,
            target_model=target_model,
        )

    lines = [f"Embedding target model: {report.target_model}"]
    summaries = []
    for summary in (report.raw_items, report.events):
        summaries.append(
            {
                "entity": summary.entity,
                "vectors": summary.vectors,
                "target_model_vectors": summary.target_model_vectors,
                "vectors_other_models": summary.vectors_other_models,
                "vectors_missing_model": summary.vectors_missing_model,
                "reembed_scope": summary.reembed_scope,
                "model_counts": [
                    {"model": entry.model, "count": entry.count} for entry in summary.model_counts
                ],
            }
        )
        lines.append(
            f"{summary.entity}: vectors={summary.vectors}, "
            f"target={summary.target_model_vectors}, "
            f"other_models={summary.vectors_other_models}, "
            f"missing_model={summary.vectors_missing_model}, "
            f"reembed_scope={summary.reembed_scope}"
        )
        lines.append(f"  model_counts: {format_embedding_model_counts(summary)}")

    lines.append(
        f"total_vectors={report.total_vectors}, "
        f"total_reembed_scope={report.total_reembed_scope}, "
        f"mixed_population={str(report.has_mixed_populations).lower()}"
    )
    exit_code = 2 if fail_on_mixed and report.has_mixed_populations else 0
    return (
        {
            "target_model": report.target_model,
            "summaries": summaries,
            "total_vectors": report.total_vectors,
            "total_reembed_scope": report.total_reembed_scope,
            "has_mixed_populations": report.has_mixed_populations,
        },
        lines,
        exit_code,
    )
