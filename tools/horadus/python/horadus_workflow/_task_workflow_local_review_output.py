from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._task_workflow_local_review_code_health import resolve_review_instructions
from ._task_workflow_local_review_constants import (
    DEFAULT_LOCAL_REVIEW_PROVIDER_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from ._task_workflow_local_review_models import LocalReviewContext


def _effective_instruction_mode(
    *,
    instructions: str | None,
    code_health_artifact_path: str | None,
) -> str:
    custom_instructions_supplied = bool(instructions and instructions.strip())
    code_health_enriched = code_health_artifact_path is not None
    if custom_instructions_supplied and code_health_enriched:
        return "custom + auto-enriched changed-file code-health context"
    if custom_instructions_supplied:
        return "custom only"
    if code_health_enriched:
        return "auto-enriched changed-file code-health context only"
    return "none"


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
        "- effective provider instructions: "
        + _effective_instruction_mode(
            instructions=instructions,
            code_health_artifact_path=code_health_artifact_path,
        ),
        f"- usefulness: {usefulness}",
        f"- raw output: {'keep' if save_raw_output else 'discard on success'}",
    ]


def prepare_review_run(
    *,
    context: LocalReviewContext,
    selected_provider: str,
    selection_source: str,
    allow_provider_fallback: bool,
    provider_attempt_order: Callable[..., list[str]],
    instructions: str | None,
    save_raw_output: bool,
    usefulness: str,
    repo_root: Path,
    run_git: Callable[[list[str]], Any],
) -> tuple[list[str], str | None, list[str]]:
    provider_order = provider_attempt_order(
        selected_provider,
        selection_source=selection_source,
        allow_provider_fallback=allow_provider_fallback,
    )
    code_health_artifact_path, effective_instructions = resolve_review_instructions(
        repo_root=repo_root,
        base_branch=context.base_branch,
        instructions=instructions,
        run_git=run_git,
    )
    return (
        provider_order,
        effective_instructions,
        build_configuration_lines(
            context=context,
            selected_provider=selected_provider,
            selection_source=selection_source,
            provider_order=provider_order,
            instructions=instructions,
            save_raw_output=save_raw_output,
            usefulness=usefulness,
            code_health_artifact_path=code_health_artifact_path,
        ),
    )
