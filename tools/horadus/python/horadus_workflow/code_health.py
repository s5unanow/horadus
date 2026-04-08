"""Deterministic code-health eval for changed tracked Python surfaces."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess  # nosec B404
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any
from uuid import uuid4

from tools.horadus.python.horadus_workflow.code_shape import (
    CodeShapePolicy,
    FileMeasurement,
    load_code_shape_policy,
    measure_python_source,
)

_DEFAULT_POLICY_PATH = Path("config/quality/code_shape.toml")
_DEFAULT_TARGET_REF = "main"
_FORMAT_VERSION = "code-health.v1"
_RESULT_PREFIX = "code-health"
_GIT_EXECUTABLE = which("git") or "/usr/bin/git"
_COMPARISON_METRICS = (
    "module_lines",
    "callable_count",
    "statement_count",
    "total_member_lines",
    "max_member_lines",
    "total_member_complexity",
    "max_member_complexity",
)


@dataclass(frozen=True, slots=True)
class CodeHealthMetrics:
    module_lines: int
    callable_count: int
    statement_count: int
    total_member_lines: int
    max_member_lines: int
    total_member_complexity: int
    max_member_complexity: int


@dataclass(frozen=True, slots=True)
class CodeHealthFileResult:
    path: str
    change_type: str
    base_metrics: CodeHealthMetrics | None
    head_metrics: CodeHealthMetrics | None
    delta: dict[str, int]
    worsened_metrics: tuple[str, ...]
    improved_metrics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CodeHealthRunResult:
    output_path: Path
    passes_validation: bool
    comparison_mode: str
    base_ref: str
    resolved_base_ref: str
    head_ref: str
    resolved_head_ref: str
    merge_base_target: str | None
    compared_files: int
    flagged_files: int
    file_results: tuple[CodeHealthFileResult, ...]


def run_code_health_eval(
    *,
    output_dir: str | Path,
    repo_root: Path,
    policy_path: str | Path = _DEFAULT_POLICY_PATH,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    merge_base_target: str = _DEFAULT_TARGET_REF,
) -> CodeHealthRunResult:
    """Compare changed tracked Python files against a base revision."""

    resolved_repo_root = repo_root.resolve()
    resolved_policy_path = (resolved_repo_root / Path(policy_path)).resolve()
    policy = load_code_shape_policy(resolved_policy_path)
    comparison_mode, resolved_base_ref = _resolve_base_ref(
        repo_root=resolved_repo_root,
        base_ref=base_ref,
        head_ref=head_ref,
        merge_base_target=merge_base_target,
    )
    resolved_head_ref = _resolve_ref(resolved_repo_root, head_ref)
    file_results = tuple(
        _build_file_result(
            repo_root=resolved_repo_root,
            record=record,
            base_ref=resolved_base_ref,
            head_ref=resolved_head_ref,
        )
        for record in _changed_python_records(
            repo_root=resolved_repo_root,
            policy=policy,
            base_ref=resolved_base_ref,
            head_ref=resolved_head_ref,
        )
    )
    passes_validation = all(not row.worsened_metrics for row in file_results)
    output_path = _write_code_health_artifact(
        output_dir=Path(output_dir),
        repo_root=resolved_repo_root,
        policy_path=resolved_policy_path,
        comparison_mode=comparison_mode,
        base_ref=base_ref or f"merge-base({merge_base_target}, {head_ref})",
        resolved_base_ref=resolved_base_ref,
        head_ref=head_ref,
        resolved_head_ref=resolved_head_ref,
        merge_base_target=None if base_ref else merge_base_target,
        file_results=file_results,
        passes_validation=passes_validation,
    )
    return CodeHealthRunResult(
        output_path=output_path,
        passes_validation=passes_validation,
        comparison_mode=comparison_mode,
        base_ref=base_ref or f"merge-base({merge_base_target}, {head_ref})",
        resolved_base_ref=resolved_base_ref,
        head_ref=head_ref,
        resolved_head_ref=resolved_head_ref,
        merge_base_target=None if base_ref else merge_base_target,
        compared_files=len(file_results),
        flagged_files=sum(1 for row in file_results if row.worsened_metrics),
        file_results=file_results,
    )


def _resolve_base_ref(
    *,
    repo_root: Path,
    base_ref: str | None,
    head_ref: str,
    merge_base_target: str,
) -> tuple[str, str]:
    if base_ref:
        return ("explicit", _resolve_ref(repo_root, base_ref))
    return (
        "merge-base",
        _run_git_command(
            repo_root,
            ("merge-base", merge_base_target, head_ref),
            error_context=f"Unable to resolve merge-base for {merge_base_target} and {head_ref}",
        ),
    )


def _resolve_ref(repo_root: Path, ref: str) -> str:
    return _run_git_command(
        repo_root,
        ("rev-parse", ref),
        error_context=f"Unable to resolve git ref '{ref}'",
    )


def _changed_python_records(
    *,
    repo_root: Path,
    policy: CodeShapePolicy,
    base_ref: str,
    head_ref: str,
) -> tuple[tuple[str, str | None, str | None], ...]:
    status_output = _run_git_command(
        repo_root,
        ("diff", "--name-status", "--find-renames=20%", base_ref, head_ref),
        error_context="Unable to determine changed files for code-health eval",
    )
    records: list[tuple[str, str | None, str | None]] = []
    for raw_line in status_output.splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) == 3:
            display_path, base_path, head_path = parts[2], parts[1], parts[2]
        elif status.startswith("D") and len(parts) >= 2:
            display_path = parts[1]
            base_path = display_path
            head_path = None
        elif len(parts) >= 2:
            display_path = parts[1]
            base_path = display_path
            head_path = display_path
        else:
            continue
        if not _is_included_python_path(display_path, policy):
            continue
        records.append((display_path, base_path, head_path))
    return tuple(sorted(records))


def _is_included_python_path(path: str, policy: CodeShapePolicy) -> bool:
    if not path.endswith(".py"):
        return False
    if not any(path == root or path.startswith(f"{root}/") for root in policy.include_roots):
        return False
    return not any(fnmatch.fnmatch(path, pattern) for pattern in policy.exclude_globs)


def _build_file_result(
    *,
    repo_root: Path,
    record: tuple[str, str | None, str | None],
    base_ref: str,
    head_ref: str,
) -> CodeHealthFileResult:
    display_path, base_path, head_path = record
    base_measurement = _measurement_for_ref(
        repo_root=repo_root,
        ref_path=base_path,
        display_path=display_path,
        ref=base_ref,
    )
    head_measurement = _measurement_for_ref(
        repo_root=repo_root,
        ref_path=head_path,
        display_path=display_path,
        ref=head_ref,
    )
    change_type = _change_type(base_measurement=base_measurement, head_measurement=head_measurement)
    base_metrics = _metrics_from_measurement(base_measurement)
    head_metrics = _metrics_from_measurement(head_measurement)
    delta = _metric_delta(base_metrics=base_metrics, head_metrics=head_metrics)
    worsened_metrics = tuple(metric for metric in _COMPARISON_METRICS if delta.get(metric, 0) > 0)
    improved_metrics = tuple(metric for metric in _COMPARISON_METRICS if delta.get(metric, 0) < 0)
    if change_type != "modified":
        worsened_metrics = ()
        improved_metrics = ()
    return CodeHealthFileResult(
        path=display_path,
        change_type=change_type,
        base_metrics=base_metrics,
        head_metrics=head_metrics,
        delta=delta,
        worsened_metrics=worsened_metrics,
        improved_metrics=improved_metrics,
    )


def _measurement_for_ref(
    *,
    repo_root: Path,
    ref_path: str | None,
    display_path: str,
    ref: str,
) -> FileMeasurement | None:
    if ref_path is None:
        return None
    blob_text = _read_blob(repo_root=repo_root, ref=ref, path=ref_path)
    if blob_text is None:
        return None
    return measure_python_source(display_path, blob_text)


def _read_blob(*, repo_root: Path, ref: str, path: str) -> str | None:
    completed = subprocess.run(  # nosec B603 - fixed git argv against repo-owned paths
        [_GIT_EXECUTABLE, "show", f"{ref}:{path}"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout


def _change_type(
    *,
    base_measurement: FileMeasurement | None,
    head_measurement: FileMeasurement | None,
) -> str:
    if base_measurement is None and head_measurement is not None:
        return "added"
    if base_measurement is not None and head_measurement is None:
        return "removed"
    return "modified"


def _metrics_from_measurement(measurement: FileMeasurement | None) -> CodeHealthMetrics | None:
    if measurement is None:
        return None
    member_lines = tuple(measurement.member_lines.values())
    member_complexities = tuple(measurement.member_complexities.values())
    return CodeHealthMetrics(
        module_lines=measurement.module_lines,
        callable_count=measurement.callable_count,
        statement_count=measurement.statement_count,
        total_member_lines=sum(member_lines),
        max_member_lines=max(member_lines, default=0),
        total_member_complexity=sum(member_complexities),
        max_member_complexity=max(member_complexities, default=0),
    )


def _metric_delta(
    *,
    base_metrics: CodeHealthMetrics | None,
    head_metrics: CodeHealthMetrics | None,
) -> dict[str, int]:
    if base_metrics is None or head_metrics is None:
        return {}
    return {
        metric: int(getattr(head_metrics, metric)) - int(getattr(base_metrics, metric))
        for metric in _COMPARISON_METRICS
    }


def _write_code_health_artifact(
    *,
    output_dir: Path,
    repo_root: Path,
    policy_path: Path,
    comparison_mode: str,
    base_ref: str,
    resolved_base_ref: str,
    head_ref: str,
    resolved_head_ref: str,
    merge_base_target: str | None,
    file_results: tuple[CodeHealthFileResult, ...],
    passes_validation: bool,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(tz=UTC)
    output_path = output_dir / (
        f"{_RESULT_PREFIX}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}.json"
    )
    payload = {
        "format_version": _FORMAT_VERSION,
        "generated_at": generated_at.isoformat(),
        "passes_validation": passes_validation,
        "comparison": {
            "mode": comparison_mode,
            "base_ref": base_ref,
            "resolved_base_ref": resolved_base_ref,
            "head_ref": head_ref,
            "resolved_head_ref": resolved_head_ref,
            "merge_base_target": merge_base_target,
        },
        "summary": {
            "compared_files": len(file_results),
            "flagged_files": sum(1 for row in file_results if row.worsened_metrics),
            "change_counts": _change_counts(file_results),
            "metrics": list(_COMPARISON_METRICS),
        },
        "provenance": {
            "source_control": _source_control_provenance(repo_root),
            "code_shape_policy": _file_manifest(policy_path),
        },
        "files": [asdict(row) for row in file_results],
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _change_counts(file_results: tuple[CodeHealthFileResult, ...]) -> dict[str, int]:
    counts = {"added": 0, "modified": 0, "removed": 0}
    for row in file_results:
        counts[row.change_type] += 1
    return counts


def _source_control_provenance(repo_root: Path) -> dict[str, Any]:
    commit_sha = _git_metadata(repo_root, ("rev-parse", "HEAD"))
    branch = _git_metadata(repo_root, ("rev-parse", "--abbrev-ref", "HEAD"))
    status_output = _git_metadata(repo_root, ("status", "--porcelain"))
    return {
        "git": {
            "available": commit_sha is not None,
            "repo_root": str(repo_root),
            "commit_sha": commit_sha,
            "branch": branch,
            "worktree_dirty": bool(status_output) if commit_sha is not None else None,
        }
    }


def _file_manifest(path: Path) -> dict[str, str]:
    raw_text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
    }


def _git_metadata(repo_root: Path, args: tuple[str, ...]) -> str | None:
    completed = subprocess.run(  # nosec B603 - fixed git argv against repo-owned paths
        [_GIT_EXECUTABLE, *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    return output or None


def _run_git_command(
    repo_root: Path,
    args: tuple[str, ...],
    *,
    error_context: str,
) -> str:
    completed = subprocess.run(  # nosec B603 - fixed git argv against repo-owned paths
        [_GIT_EXECUTABLE, *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ValueError(f"{error_context}: {message}")
    return completed.stdout.strip()


__all__ = [
    "CodeHealthFileResult",
    "CodeHealthMetrics",
    "CodeHealthRunResult",
    "run_code_health_eval",
]
