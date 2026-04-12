from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.horadus.python.horadus_workflow._docs_freshness_planning_hotspots import (
    hotspot_outcome_marker_value,
    hotspot_outcome_marker_values,
    matching_allowlisted_hotspot_paths,
    parse_hotspot_outcome_marker,
)


def hotspot_outcome_from_relative_path(
    *, repo_root: Path, relative_path: str
) -> tuple[str | None, str | None]:
    path = repo_root / relative_path
    if not path.exists():
        return None, None
    content = path.read_text(encoding="utf-8")
    marker_values = hotspot_outcome_marker_values(content)
    if len(marker_values) != 1:
        return None, None
    value = hotspot_outcome_marker_value(content)
    if parse_hotspot_outcome_marker(value) is None:
        return None, None
    return value, relative_path if value is not None else None


def build_planning_context(
    *,
    task_id: str,
    record: Any,
    repo_root: Path,
    backlog_path_display: str,
    spec_paths: list[str],
    exec_plan_paths: tuple[str, ...],
    normalized_paths: list[str],
    canonical_example_path: str,
    planning_marker_from_relative_path: Callable[[str], tuple[str | None, str | None]],
    task_planning_gates_value: Callable[[Any], str | None],
    planning_gates_required: Callable[[str | None], bool | None],
    task_requires_exec_plan: Callable[[Any], bool],
) -> dict[str, object]:
    hotspot_paths = list(matching_allowlisted_hotspot_paths(repo_root, normalized_paths))
    explicit_value, marker_source = _planning_marker_metadata(
        record=record,
        backlog_path_display=backlog_path_display,
        spec_paths=spec_paths,
        exec_plan_paths=exec_plan_paths,
        planning_marker_from_relative_path=planning_marker_from_relative_path,
        task_planning_gates_value=task_planning_gates_value,
    )
    required = planning_gates_required(explicit_value)
    if required is None:
        required = task_requires_exec_plan(record) or bool(exec_plan_paths)
    if hotspot_paths:
        required = True
    if not required:
        return _planning_context_payload(
            required=False,
            state="non_applicable",
            marker_value=explicit_value,
            marker_source=marker_source,
            authoritative_artifact_path=None,
            gate_home_path=None,
            waiver_home_path=None,
            missing_artifact_notice=None,
            canonical_example_path=canonical_example_path,
            spec_paths=spec_paths,
            exec_plan_paths=exec_plan_paths,
            hotspot_paths=hotspot_paths,
            hotspot_outcome_value=None,
            hotspot_outcome_source=None,
            hotspot_outcome_notice=None,
        )
    if exec_plan_paths:
        return _authoritative_planning_context(
            state="applicable_with_authoritative_artifact_present",
            authoritative_path=exec_plan_paths[0],
            gate_home_path=spec_paths[0] if spec_paths else exec_plan_paths[0],
            marker_value=explicit_value,
            marker_source=marker_source,
            canonical_example_path=canonical_example_path,
            spec_paths=spec_paths,
            exec_plan_paths=exec_plan_paths,
            hotspot_paths=hotspot_paths,
            repo_root=repo_root,
        )
    if spec_paths:
        return _authoritative_planning_context(
            state="applicable_spec_backed_without_exec_plan",
            authoritative_path=spec_paths[0],
            gate_home_path=spec_paths[0],
            marker_value=explicit_value,
            marker_source=marker_source or spec_paths[0],
            canonical_example_path=canonical_example_path,
            spec_paths=spec_paths,
            exec_plan_paths=exec_plan_paths,
            hotspot_paths=hotspot_paths,
            repo_root=repo_root,
        )
    notice = (
        f"{task_id} requires planning gates, but no spec or exec plan exists yet. "
        "Add a task spec or exec plan before implementation; backlog markers do not "
        "replace the Phase -1 gates or Gate Outcomes / Waivers sections."
    )
    return _planning_context_payload(
        required=True,
        state="applicable_backlog_only_missing_artifact",
        marker_value=explicit_value,
        marker_source=marker_source or backlog_path_display,
        authoritative_artifact_path=None,
        gate_home_path=None,
        waiver_home_path=None,
        missing_artifact_notice=notice,
        canonical_example_path=canonical_example_path,
        spec_paths=spec_paths,
        exec_plan_paths=exec_plan_paths,
        hotspot_paths=hotspot_paths,
        hotspot_outcome_value=None,
        hotspot_outcome_source=None,
        hotspot_outcome_notice=_hotspot_outcome_notice(
            hotspot_paths=hotspot_paths,
            authoritative_path=None,
            hotspot_outcome_value=None,
        ),
    )


def _planning_marker_metadata(
    *,
    record: Any,
    backlog_path_display: str,
    spec_paths: list[str],
    exec_plan_paths: tuple[str, ...],
    planning_marker_from_relative_path: Callable[[str], tuple[str | None, str | None]],
    task_planning_gates_value: Callable[[Any], str | None],
) -> tuple[str | None, str | None]:
    for relative_path in [*exec_plan_paths, *spec_paths]:
        explicit_value, marker_source = planning_marker_from_relative_path(relative_path)
        if explicit_value is not None:
            return explicit_value, marker_source
    explicit_value = task_planning_gates_value(record)
    if explicit_value is None:
        return None, None
    return explicit_value, record.source_path or backlog_path_display


def _authoritative_planning_context(
    *,
    state: str,
    authoritative_path: str,
    gate_home_path: str,
    marker_value: str | None,
    marker_source: str | None,
    canonical_example_path: str,
    spec_paths: list[str],
    exec_plan_paths: tuple[str, ...],
    hotspot_paths: list[str],
    repo_root: Path,
) -> dict[str, object]:
    hotspot_outcome_value, hotspot_outcome_source = hotspot_outcome_from_relative_path(
        repo_root=repo_root,
        relative_path=authoritative_path,
    )
    return _planning_context_payload(
        required=True,
        state=state,
        marker_value=marker_value,
        marker_source=marker_source,
        authoritative_artifact_path=authoritative_path,
        gate_home_path=gate_home_path,
        waiver_home_path=authoritative_path,
        missing_artifact_notice=None,
        canonical_example_path=canonical_example_path,
        spec_paths=spec_paths,
        exec_plan_paths=exec_plan_paths,
        hotspot_paths=hotspot_paths,
        hotspot_outcome_value=hotspot_outcome_value,
        hotspot_outcome_source=hotspot_outcome_source,
        hotspot_outcome_notice=_hotspot_outcome_notice(
            hotspot_paths=hotspot_paths,
            authoritative_path=authoritative_path,
            hotspot_outcome_value=hotspot_outcome_value,
        ),
    )


def _planning_context_payload(
    *,
    required: bool,
    state: str,
    marker_value: str | None,
    marker_source: str | None,
    authoritative_artifact_path: str | None,
    gate_home_path: str | None,
    waiver_home_path: str | None,
    missing_artifact_notice: str | None,
    canonical_example_path: str,
    spec_paths: list[str],
    exec_plan_paths: tuple[str, ...],
    hotspot_paths: list[str],
    hotspot_outcome_value: str | None,
    hotspot_outcome_source: str | None,
    hotspot_outcome_notice: str | None,
) -> dict[str, object]:
    return {
        "required": required,
        "state": state,
        "marker_value": marker_value,
        "marker_source": marker_source,
        "authoritative_artifact_path": authoritative_artifact_path,
        "gate_home_path": gate_home_path,
        "waiver_home_path": waiver_home_path,
        "missing_artifact_notice": missing_artifact_notice,
        "canonical_example_path": canonical_example_path,
        "spec_paths": spec_paths,
        "exec_plan_paths": exec_plan_paths,
        "hotspot_paths": hotspot_paths,
        "hotspot_outcome_required": bool(hotspot_paths),
        "hotspot_outcome_value": hotspot_outcome_value,
        "hotspot_outcome_source": hotspot_outcome_source,
        "hotspot_outcome_notice": hotspot_outcome_notice,
    }


def _hotspot_outcome_notice(
    *,
    hotspot_paths: list[str],
    authoritative_path: str | None,
    hotspot_outcome_value: str | None,
) -> str | None:
    if not hotspot_paths or hotspot_outcome_value is not None:
        return None
    if authoritative_path is None:
        return (
            "This task declares allowlisted production hotspots. Create the missing planning "
            "artifact first, then add `- Hotspot Outcome: reduce — ...` or "
            "`- Hotspot Outcome: keep-flat-with-rationale — ...` or "
            "`- Hotspot Outcome: follow-up-task-created — TASK-XXX ...`."
        )
    return (
        "This task declares allowlisted production hotspots. Add "
        "`- Hotspot Outcome: reduce — ...` or "
        "`- Hotspot Outcome: keep-flat-with-rationale — ...` or "
        "`- Hotspot Outcome: follow-up-task-created — TASK-XXX ...` to "
        f"{authoritative_path}."
    )


__all__ = ["build_planning_context", "hotspot_outcome_from_relative_path"]
