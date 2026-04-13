from __future__ import annotations

from typing import TYPE_CHECKING

from ._task_workflow_local_review_constants import (
    DEFAULT_LOCAL_REVIEW_PROVIDER_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from ._task_workflow_local_review_models import LocalReviewContext


def build_configuration_lines(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    provider_order: list[str],
    instructions: str | None,
    save_raw_output: bool,
    usefulness: str,
    code_health_artifact_path: str | None,
) -> list[str]:
    return [
        "Local review configuration:",
        f"- provider: {selected_provider} (source={selection_source})",
        f"- provider order: {', '.join(provider_order)}",
        f"- base branch: {context.base_branch}",
        f"- target: {context.review_target_value}",
        f"- provider timeout: {DEFAULT_LOCAL_REVIEW_PROVIDER_TIMEOUT_SECONDS}s",
        f"- changed-file code-health: {code_health_artifact_path or 'not available'}",
        f"- instructions supplied: {'yes' if instructions and instructions.strip() else 'no'}",
        f"- usefulness: {usefulness}",
        f"- raw output: {'keep' if save_raw_output else 'discard on success'}",
    ]
