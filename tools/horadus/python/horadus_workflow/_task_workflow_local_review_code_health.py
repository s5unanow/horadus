from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

_CODE_HEALTH_RESULTS_DIR = Path("ai/eval/results")
_CODE_HEALTH_RESULT_PREFIX = "code-health-"
_CODE_HEALTH_FORMAT_VERSION = "code-health.v1"
_MAX_FLAGGED_FILES = 3


def load_code_health_prompt_context(
    *,
    repo_root: Path,
    resolved_base_ref: str,
    resolved_head_ref: str,
) -> tuple[str | None, str | None]:
    artifact_path = _latest_matching_artifact(
        repo_root=repo_root,
        resolved_base_ref=resolved_base_ref,
        resolved_head_ref=resolved_head_ref,
    )
    if artifact_path is None:
        return (None, None)
    payload = _load_json(artifact_path)
    if payload is None:
        return (None, None)
    return (
        str(artifact_path.relative_to(repo_root)),
        _render_code_health_summary(payload),
    )


def augment_review_instructions(
    instructions: str | None,
    *,
    artifact_path: str | None,
    summary: str | None,
) -> str | None:
    code_health_notes = _code_health_review_instructions(
        artifact_path=artifact_path,
        summary=summary,
    )
    if code_health_notes is None:
        return instructions
    if instructions and instructions.strip():
        return f"{instructions.strip()}\n\n{code_health_notes}"
    return code_health_notes


def resolve_review_instructions(
    *,
    repo_root: Path,
    base_branch: str,
    instructions: str | None,
    run_git: Callable[[list[str]], Any],
) -> tuple[str | None, str | None]:
    head_result = run_git(["rev-parse", "--verify", "HEAD"])
    merge_base_result = run_git(["merge-base", base_branch, "HEAD"])
    artifact_path = summary = None
    if head_result.returncode == 0 and merge_base_result.returncode == 0:
        artifact_path, summary = load_code_health_prompt_context(
            repo_root=repo_root,
            resolved_base_ref=merge_base_result.stdout.strip(),
            resolved_head_ref=head_result.stdout.strip(),
        )
    return artifact_path, augment_review_instructions(
        instructions,
        artifact_path=artifact_path,
        summary=summary,
    )


def _latest_matching_artifact(
    *,
    repo_root: Path,
    resolved_base_ref: str,
    resolved_head_ref: str,
) -> Path | None:
    results_dir = repo_root / _CODE_HEALTH_RESULTS_DIR
    if not results_dir.is_dir():
        return None
    candidates = sorted(results_dir.glob(f"{_CODE_HEALTH_RESULT_PREFIX}*.json"), reverse=True)
    for path in candidates:
        payload = _load_json(path)
        if _matches_refs(
            payload=payload,
            resolved_base_ref=resolved_base_ref,
            resolved_head_ref=resolved_head_ref,
        ):
            return path
    return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _matches_refs(
    *,
    payload: dict[str, Any] | None,
    resolved_base_ref: str,
    resolved_head_ref: str,
) -> bool:
    if payload is None or payload.get("format_version") != _CODE_HEALTH_FORMAT_VERSION:
        return False
    comparison = payload.get("comparison")
    if not isinstance(comparison, dict):
        return False
    return (
        comparison.get("resolved_base_ref") == resolved_base_ref
        and comparison.get("resolved_head_ref") == resolved_head_ref
    )


def _render_code_health_summary(payload: dict[str, Any]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return "Changed-file code-health artifact was present, but its summary was unreadable."
    compared_files = int(summary.get("compared_files", 0))
    flagged_files = int(summary.get("flagged_files", 0))
    lines = [
        f"Compared tracked Python files: {compared_files}; flagged regressions: {flagged_files}.",
    ]
    if compared_files == 0:
        lines.append("No tracked Python files were included in the code-health eval.")
        return "\n".join(lines)
    if flagged_files == 0:
        lines.append("No structural regressions were flagged by the code-health eval.")
        return "\n".join(lines)
    files = payload.get("files")
    if not isinstance(files, list):
        lines.append("Flagged file details were unavailable.")
        return "\n".join(lines)
    flagged_rows = [row for row in files if isinstance(row, dict) and _worsened_metrics(row)]
    for row in flagged_rows[:_MAX_FLAGGED_FILES]:
        lines.append(_render_flagged_file_line(row))
    remaining = len(flagged_rows) - min(len(flagged_rows), _MAX_FLAGGED_FILES)
    if remaining > 0:
        lines.append(f"{remaining} more flagged file(s) omitted from the prompt summary.")
    return "\n".join(lines)


def _render_flagged_file_line(row: dict[str, Any]) -> str:
    path = str(row.get("path", "(unknown path)"))
    delta = row.get("delta")
    delta_map = delta if isinstance(delta, dict) else {}
    metrics = ", ".join(
        f"{metric} ({_signed_delta(delta_map.get(metric))})" for metric in _worsened_metrics(row)
    )
    return f"{path}: worsened {metrics}"


def _worsened_metrics(row: dict[str, Any]) -> list[str]:
    metrics = row.get("worsened_metrics")
    if not isinstance(metrics, list):
        return []
    return [str(metric) for metric in metrics]


def _signed_delta(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"+{number}" if number >= 0 else str(number)


def _code_health_review_instructions(
    *,
    artifact_path: str | None,
    summary: str | None,
) -> str | None:
    if not summary:
        return None
    lines = [
        "Use the changed-file code-health summary below as structural context instead of rediscovering the same signals from the diff alone.",
    ]
    if artifact_path:
        lines.append(f"Changed-file code-health artifact: {artifact_path}")
    lines.extend(["Changed-file code-health summary:", summary])
    return "\n".join(lines)
