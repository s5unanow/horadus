from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.horadus.python.horadus_workflow._docs_freshness_planning import (
    _hotspot_outcome_marker_value,
    _matching_allowlisted_hotspot_paths,
)


def hotspot_outcome_from_relative_path(
    *, repo_root: Path, relative_path: str
) -> tuple[str | None, str | None]:
    path = repo_root / relative_path
    if not path.exists():
        return None, None
    value = _hotspot_outcome_marker_value(path.read_text(encoding="utf-8"))
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
    hotspot_paths = list(_matching_allowlisted_hotspot_paths(repo_root, normalized_paths))
    explicit_value = None
    marker_source = None
    for relative_path in [*exec_plan_paths, *spec_paths]:
        explicit_value, marker_source = planning_marker_from_relative_path(relative_path)
        if explicit_value is not None:
            break
    if explicit_value is None:
        explicit_value = task_planning_gates_value(record)
        if explicit_value is not None:
            marker_source = record.source_path or backlog_path_display

    required = planning_gates_required(explicit_value)
    if required is None:
        required = task_requires_exec_plan(record) or bool(exec_plan_paths)
    if hotspot_paths:
        required = True

    if not required:
        return {
            "required": False,
            "state": "non_applicable",
            "marker_value": explicit_value,
            "marker_source": marker_source,
            "authoritative_artifact_path": None,
            "gate_home_path": None,
            "waiver_home_path": None,
            "missing_artifact_notice": None,
            "canonical_example_path": canonical_example_path,
            "spec_paths": spec_paths,
            "exec_plan_paths": exec_plan_paths,
            "hotspot_paths": hotspot_paths,
            "hotspot_outcome_required": False,
            "hotspot_outcome_value": None,
            "hotspot_outcome_source": None,
            "hotspot_outcome_notice": None,
        }

    if exec_plan_paths:
        gate_home_path = spec_paths[0] if spec_paths else exec_plan_paths[0]
        hotspot_outcome_value, hotspot_outcome_source = hotspot_outcome_from_relative_path(
            repo_root=repo_root,
            relative_path=exec_plan_paths[0],
        )
        return {
            "required": True,
            "state": "applicable_with_authoritative_artifact_present",
            "marker_value": explicit_value,
            "marker_source": marker_source,
            "authoritative_artifact_path": exec_plan_paths[0],
            "gate_home_path": gate_home_path,
            "waiver_home_path": exec_plan_paths[0],
            "missing_artifact_notice": None,
            "canonical_example_path": canonical_example_path,
            "spec_paths": spec_paths,
            "exec_plan_paths": exec_plan_paths,
            "hotspot_paths": hotspot_paths,
            "hotspot_outcome_required": bool(hotspot_paths),
            "hotspot_outcome_value": hotspot_outcome_value,
            "hotspot_outcome_source": hotspot_outcome_source,
            "hotspot_outcome_notice": _hotspot_outcome_notice(
                hotspot_paths=hotspot_paths,
                authoritative_path=exec_plan_paths[0],
                hotspot_outcome_value=hotspot_outcome_value,
            ),
        }

    if spec_paths:
        hotspot_outcome_value, hotspot_outcome_source = hotspot_outcome_from_relative_path(
            repo_root=repo_root,
            relative_path=spec_paths[0],
        )
        return {
            "required": True,
            "state": "applicable_spec_backed_without_exec_plan",
            "marker_value": explicit_value,
            "marker_source": marker_source or spec_paths[0],
            "authoritative_artifact_path": spec_paths[0],
            "gate_home_path": spec_paths[0],
            "waiver_home_path": spec_paths[0],
            "missing_artifact_notice": None,
            "canonical_example_path": canonical_example_path,
            "spec_paths": spec_paths,
            "exec_plan_paths": exec_plan_paths,
            "hotspot_paths": hotspot_paths,
            "hotspot_outcome_required": bool(hotspot_paths),
            "hotspot_outcome_value": hotspot_outcome_value,
            "hotspot_outcome_source": hotspot_outcome_source,
            "hotspot_outcome_notice": _hotspot_outcome_notice(
                hotspot_paths=hotspot_paths,
                authoritative_path=spec_paths[0],
                hotspot_outcome_value=hotspot_outcome_value,
            ),
        }

    notice = (
        f"{task_id} requires planning gates, but no spec or exec plan exists yet. "
        "Add a task spec or exec plan before implementation; backlog markers do not "
        "replace the Phase -1 gates or Gate Outcomes / Waivers sections."
    )
    return {
        "required": True,
        "state": "applicable_backlog_only_missing_artifact",
        "marker_value": explicit_value,
        "marker_source": marker_source or backlog_path_display,
        "authoritative_artifact_path": None,
        "gate_home_path": None,
        "waiver_home_path": None,
        "missing_artifact_notice": notice,
        "canonical_example_path": canonical_example_path,
        "spec_paths": spec_paths,
        "exec_plan_paths": exec_plan_paths,
        "hotspot_paths": hotspot_paths,
        "hotspot_outcome_required": bool(hotspot_paths),
        "hotspot_outcome_value": None,
        "hotspot_outcome_source": None,
        "hotspot_outcome_notice": _hotspot_outcome_notice(
            hotspot_paths=hotspot_paths,
            authoritative_path=None,
            hotspot_outcome_value=None,
        ),
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
