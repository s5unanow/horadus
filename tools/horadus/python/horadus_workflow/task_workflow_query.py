from __future__ import annotations

from dataclasses import asdict
from typing import Any, TypedDict

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared
from tools.horadus.python.horadus_workflow.result import CommandResult, ExitCode
from tools.horadus.python.horadus_workflow.task_workflow_policy import (
    canonical_task_workflow_commands_for_task,
    high_risk_pre_push_review_batching_statements,
    high_risk_pre_push_review_commands,
    high_risk_pre_push_review_fallback_statements,
)

_CANONICAL_PLANNING_EXAMPLE_PATH = "tasks/specs/275-finish-review-gate-timeout.md"
_PLANNING_STATE_PRESENT = "applicable_with_authoritative_artifact_present"
_PLANNING_STATE_SPEC_ONLY = "applicable_spec_backed_without_exec_plan"
_PLANNING_STATE_MISSING = "applicable_backlog_only_missing_artifact"
_PLANNING_STATE_QUIET = "non_applicable"
_HIGH_RISK_SHARED_WORKFLOW_PREFIXES = (
    "tools/horadus/python/horadus_workflow/",
    "tools/horadus/python/horadus_cli/",
)
_HIGH_RISK_POLICY_FILES = ("AGENTS.md", "docs/AGENT_RUNBOOK.md", "tasks/specs/TEMPLATE.md")
_HIGH_RISK_RUNTIME_SURFACE_PREFIXES = {
    "src/api/": "api",
    "src/core/": "core",
    "src/ingestion/": "ingestion",
    "src/processing/": "processing",
    "src/storage/": "storage",
    "src/workers/": "workers",
    "alembic/": "migrations",
}
_HIGH_RISK_TEXT_MARKERS = (
    ("migration", "task description references migrations"),
    ("migrations", "task description references migrations"),
    ("shared math", "task description references shared math"),
    ("workflow tooling", "task description references workflow tooling"),
    ("multi-surface mutation", "task description references multi-surface mutation paths"),
    ("cross-surface", "task description references cross-surface behavior"),
)
_SUGGESTED_VALIDATION_COMMANDS = [
    "make agent-check",
    "uv run --no-sync horadus tasks local-gate --full",
]


class PrePushReviewGuidance(TypedDict):
    recommended: bool
    risk_reasons: list[str]
    commands: list[str]
    fallback_notes: list[str]
    batching_notes: list[str]


def _task_record_payload(record: Any, *, include_raw: bool = True) -> dict[str, object]:
    backlog_path = shared._compat_attr("backlog_path", task_repo)
    current_sprint_path = shared._compat_attr("current_sprint_path", task_repo)
    repo_root = shared._compat_attr("repo_root", task_repo)
    payload = asdict(record)
    if not include_raw:
        payload.pop("raw_block", None)
    payload["backlog_path"] = payload.get("source_path") or str(
        backlog_path().relative_to(repo_root())
    )
    payload["current_sprint_path"] = str(current_sprint_path().relative_to(repo_root()))
    return payload


def _archived_task_blocked_result(task_id: str) -> CommandResult:
    return CommandResult(
        exit_code=ExitCode.NOT_FOUND,
        error_lines=[
            f"{task_id} is archived; re-run with --include-archive to inspect its history"
        ],
        data={"task_id": task_id, "archived": True},
    )


def handle_list_active(_args: Any) -> CommandResult:
    parse_active_tasks = shared._compat_attr("parse_active_tasks", task_repo)
    parse_human_blockers = shared._compat_attr("parse_human_blockers", task_repo)
    tasks = parse_active_tasks()
    active_task_ids = {task.task_id for task in tasks}
    blockers = parse_human_blockers(task_ids=active_task_ids)
    blockers_by_task = {blocker.task_id: blocker for blocker in blockers}
    overdue_blockers = [
        blocker
        for blocker in blockers
        if blocker.urgency is not None and blocker.urgency.is_overdue
    ]
    lines = ["Active tasks:"]
    for task in tasks:
        suffix = " [REQUIRES_HUMAN]" if task.requires_human else ""
        note = f" — {task.note}" if task.note else ""
        urgency_note = ""
        blocker = blockers_by_task.get(task.task_id)
        if blocker is not None and blocker.urgency is not None:
            if blocker.urgency.is_overdue:
                overdue_days = abs(blocker.urgency.days_until_next_action or 0)
                urgency_note = f" [OVERDUE by {overdue_days}d]"
            elif blocker.urgency.is_due_today:
                urgency_note = " [DUE TODAY]"
        lines.append(f"- {task.task_id}: {task.title}{suffix}{urgency_note}{note}")
    if overdue_blockers:
        lines.append(
            "- overdue_human_blockers="
            f"{len(overdue_blockers)} ({', '.join(blocker.task_id for blocker in overdue_blockers)})"
        )
    return CommandResult(
        lines=lines,
        data={
            "tasks": [asdict(task) for task in tasks],
            "human_blockers": [asdict(item) for item in blockers],
            "overdue_human_blockers": [asdict(item) for item in overdue_blockers],
        },
    )


def handle_show(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    include_archive = bool(getattr(args, "include_archive", False))
    task_record = shared._compat_attr("task_record", task_repo)
    archived_task_record = shared._compat_attr("archived_task_record", task_repo)
    record = task_record(task_id, include_archive=include_archive)
    if record is None:
        if not include_archive and archived_task_record(task_id) is not None:
            return _archived_task_blocked_result(task_id)
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    lines = [
        f"# {record.task_id}: {record.title}",
        f"Status: {record.status}",
        f"Priority: {record.priority or 'unknown'}",
        f"Estimate: {record.estimate or 'unknown'}",
    ]
    if record.description:
        lines.append("Description:")
        lines.extend(f"- {item}" for item in record.description)
    if record.files:
        lines.append("Files:")
        lines.extend(f"- {item}" for item in record.files)
    if record.acceptance_criteria:
        lines.append("Acceptance Criteria:")
        lines.extend(record.acceptance_criteria)
    if record.spec_paths:
        lines.append("Specs:")
        lines.extend(f"- {item}" for item in record.spec_paths)
    return CommandResult(lines=lines, data=_task_record_payload(record))


def handle_search(args: Any) -> CommandResult:
    if args.limit is not None and args.limit < 1:
        return CommandResult(
            exit_code=ExitCode.VALIDATION_ERROR,
            error_lines=["--limit must be a positive integer"],
        )

    query = " ".join(args.query).strip()
    include_archive = bool(getattr(args, "include_archive", False))
    search_task_records = shared._compat_attr("search_task_records", task_repo)
    matches = search_task_records(
        query,
        status=args.status,
        limit=args.limit,
        include_archive=include_archive,
    )
    lines = [f"Task search: {query}"]
    lines.append(
        f"- status={args.status}, limit={args.limit if args.limit is not None else 'none'}, "
        f"include_archive={'yes' if include_archive else 'no'}, results={len(matches)}"
    )
    if not matches:
        lines.append("(no matches)")
    else:
        for record in matches:
            lines.append(
                f"- {record.task_id}: {record.title} [{record.status}] "
                f"(priority={record.priority or 'unknown'}, estimate={record.estimate or 'unknown'})"
            )
        if args.include_raw:
            for record in matches:
                lines.extend(["", f"## {record.task_id}", record.raw_block])
    return CommandResult(
        lines=lines,
        data={
            "query": query,
            "status_filter": args.status,
            "limit": args.limit,
            "include_archive": include_archive,
            "include_raw": bool(args.include_raw),
            "matches": [
                _task_record_payload(item, include_raw=bool(args.include_raw)) for item in matches
            ],
        },
    )


def _workflow_commands_for_context_pack(
    task_id: str,
    *,
    include_archive: bool,
    archived: bool,
) -> list[str]:
    commands = list(canonical_task_workflow_commands_for_task(task_id))
    if not (include_archive and archived):
        return commands

    default_context_pack = f"uv run --no-sync horadus tasks context-pack {task_id}"
    archived_context_pack = f"{default_context_pack} --include-archive"
    return [
        archived_context_pack if command == default_context_pack else command
        for command in commands
    ]


def _planning_marker_from_relative_path(relative_path: str) -> tuple[str | None, str | None]:
    repo_root = shared._compat_attr("repo_root", task_repo)
    planning_gates_value_from_text = shared._compat_attr(
        "planning_gates_value_from_text", task_repo
    )
    path = repo_root() / relative_path
    if not path.exists():
        return None, None
    value = planning_gates_value_from_text(path.read_text(encoding="utf-8"))
    return value, relative_path


def _planning_context(task_id: str, record: Any) -> dict[str, object]:
    spec_paths_for_task = shared._compat_attr("spec_paths_for_task", task_repo)
    exec_plan_paths_for_task = shared._compat_attr("exec_plan_paths_for_task", task_repo)
    task_planning_gates_value = shared._compat_attr("task_planning_gates_value", task_repo)
    planning_gates_required = shared._compat_attr("planning_gates_required", task_repo)
    task_requires_exec_plan = shared._compat_attr("task_requires_exec_plan", task_repo)
    backlog_path = shared._compat_attr("backlog_path", task_repo)
    repo_root = shared._compat_attr("repo_root", task_repo)
    spec_paths = list(record.spec_paths or spec_paths_for_task(task_id))
    exec_plan_paths = exec_plan_paths_for_task(task_id)

    explicit_value = None
    marker_source = None
    for relative_path in [*exec_plan_paths, *spec_paths]:
        explicit_value, marker_source = _planning_marker_from_relative_path(relative_path)
        if explicit_value is not None:
            break
    if explicit_value is None:
        explicit_value = task_planning_gates_value(record)
        if explicit_value is not None:
            marker_source = record.source_path or str(backlog_path().relative_to(repo_root()))

    required = planning_gates_required(explicit_value)
    if required is None:
        required = task_requires_exec_plan(record) or bool(exec_plan_paths)

    if not required:
        return {
            "required": False,
            "state": _PLANNING_STATE_QUIET,
            "marker_value": explicit_value,
            "marker_source": marker_source,
            "authoritative_artifact_path": None,
            "gate_home_path": None,
            "waiver_home_path": None,
            "missing_artifact_notice": None,
            "canonical_example_path": _CANONICAL_PLANNING_EXAMPLE_PATH,
            "spec_paths": spec_paths,
            "exec_plan_paths": exec_plan_paths,
        }

    if exec_plan_paths:
        gate_home_path = spec_paths[0] if spec_paths else exec_plan_paths[0]
        return {
            "required": True,
            "state": _PLANNING_STATE_PRESENT,
            "marker_value": explicit_value,
            "marker_source": marker_source,
            "authoritative_artifact_path": exec_plan_paths[0],
            "gate_home_path": gate_home_path,
            "waiver_home_path": exec_plan_paths[0],
            "missing_artifact_notice": None,
            "canonical_example_path": _CANONICAL_PLANNING_EXAMPLE_PATH,
            "spec_paths": spec_paths,
            "exec_plan_paths": exec_plan_paths,
        }

    if spec_paths:
        return {
            "required": True,
            "state": _PLANNING_STATE_SPEC_ONLY,
            "marker_value": explicit_value,
            "marker_source": marker_source or spec_paths[0],
            "authoritative_artifact_path": spec_paths[0],
            "gate_home_path": spec_paths[0],
            "waiver_home_path": spec_paths[0],
            "missing_artifact_notice": None,
            "canonical_example_path": _CANONICAL_PLANNING_EXAMPLE_PATH,
            "spec_paths": spec_paths,
            "exec_plan_paths": exec_plan_paths,
        }

    notice = (
        f"{task_id} requires planning gates, but no spec or exec plan exists yet. "
        "Add a task spec or exec plan before implementation; backlog markers do not "
        "replace the Phase -1 gates or Gate Outcomes / Waivers sections."
    )
    return {
        "required": True,
        "state": _PLANNING_STATE_MISSING,
        "marker_value": explicit_value,
        "marker_source": marker_source
        or record.source_path
        or str(backlog_path().relative_to(repo_root())),
        "authoritative_artifact_path": None,
        "gate_home_path": None,
        "waiver_home_path": None,
        "missing_artifact_notice": notice,
        "canonical_example_path": _CANONICAL_PLANNING_EXAMPLE_PATH,
        "spec_paths": spec_paths,
        "exec_plan_paths": exec_plan_paths,
    }


def _normalized_task_paths(record: Any) -> list[str]:
    return [path.strip().strip("`") for path in record.files or [] if path.strip().strip("`")]


def _pre_push_review_guidance(record: Any) -> PrePushReviewGuidance:
    normalized_paths = _normalized_task_paths(record)
    risk_reasons: list[str] = []
    runtime_surfaces = sorted(
        {
            label
            for path in normalized_paths
            for prefix, label in _HIGH_RISK_RUNTIME_SURFACE_PREFIXES.items()
            if path.startswith(prefix)
        }
    )

    if any(path.startswith("alembic/") for path in normalized_paths):
        risk_reasons.append("task touches migration surfaces")

    if any(
        path == policy_path for policy_path in _HIGH_RISK_POLICY_FILES for path in normalized_paths
    ):
        risk_reasons.append("task changes canonical workflow or policy guidance")

    if any(
        path.startswith(prefix)
        for prefix in _HIGH_RISK_SHARED_WORKFLOW_PREFIXES
        for path in normalized_paths
    ):
        risk_reasons.append("task changes shared workflow tooling")

    if len(runtime_surfaces) >= 2:
        risk_reasons.append("task spans multiple runtime surfaces: " + ", ".join(runtime_surfaces))

    text_blob = " ".join([record.title, *record.description, *record.acceptance_criteria]).lower()
    for marker, reason in _HIGH_RISK_TEXT_MARKERS:
        if marker in text_blob and reason not in risk_reasons:
            risk_reasons.append(reason)

    recommended = bool(risk_reasons)
    return {
        "recommended": recommended,
        "risk_reasons": risk_reasons,
        "commands": list(high_risk_pre_push_review_commands()) if recommended else [],
        "fallback_notes": (
            list(high_risk_pre_push_review_fallback_statements()) if recommended else []
        ),
        "batching_notes": (
            list(high_risk_pre_push_review_batching_statements()) if recommended else []
        ),
    }


def _append_pre_push_review_guidance_lines(
    lines: list[str], guidance: PrePushReviewGuidance
) -> None:
    if not guidance["recommended"]:
        return
    lines.extend(["", "## Pre-Push Review Guidance", "Applicability: recommended"])
    lines.extend(f"- {reason}" for reason in guidance["risk_reasons"])
    lines.extend(["", "Suggested commands:"])
    lines.extend(guidance["commands"])
    lines.extend(["", "Fallback guidance:"])
    lines.extend(f"- {note}" for note in guidance["fallback_notes"])
    lines.extend(["", "Re-review discipline:"])
    lines.extend(f"- {note}" for note in guidance["batching_notes"])


def handle_context_pack(args: Any) -> CommandResult:
    try:
        task_id = task_repo.normalize_task_id(args.task_id)
    except ValueError as exc:
        return CommandResult(exit_code=ExitCode.VALIDATION_ERROR, error_lines=[str(exc)])

    include_archive = bool(getattr(args, "include_archive", False))
    task_record = shared._compat_attr("task_record", task_repo)
    archived_task_record = shared._compat_attr("archived_task_record", task_repo)
    record = task_record(task_id, include_archive=include_archive)
    if record is None:
        if not include_archive and archived_task_record(task_id) is not None:
            return _archived_task_blocked_result(task_id)
        return CommandResult(
            exit_code=ExitCode.NOT_FOUND,
            error_lines=[f"{task_id} not found in tasks/BACKLOG.md"],
            data={"task_id": task_id},
        )

    planning = _planning_context(task_id, record)
    pre_push_review = _pre_push_review_guidance(record)
    lines = [
        f"# Context Pack: {task_id}",
        "",
        "## Backlog Entry",
        record.raw_block,
        "",
        "## Sprint Status",
    ]
    lines.extend(record.sprint_lines or ["(not listed in current sprint)"])
    lines.extend(["", "## Matching Spec"])
    lines.extend(record.spec_paths or ["(none)"])
    lines.extend(
        [
            "",
            "## Spec Contract Template",
            "tasks/specs/TEMPLATE.md",
            _CANONICAL_PLANNING_EXAMPLE_PATH,
        ]
    )
    if planning["required"]:
        lines.extend(
            [
                "",
                "## Planning Gates",
                "Applicability: required",
                f"State: {planning['state']}",
            ]
        )
        if planning["marker_value"] is not None:
            lines.append(
                f"Marker: {planning['marker_value']} ({planning['marker_source'] or 'unknown source'})"
            )
        if planning["authoritative_artifact_path"] is not None:
            lines.append(
                f"Authoritative planning artifact: {planning['authoritative_artifact_path']}"
            )
        if planning["gate_home_path"] is not None:
            lines.append(f"Phase -1 gates home: {planning['gate_home_path']}")
        if planning["waiver_home_path"] is not None:
            lines.append(f"Gate Outcomes / Waivers home: {planning['waiver_home_path']}")
        if planning["missing_artifact_notice"] is not None:
            lines.append(f"Missing artifact notice: {planning['missing_artifact_notice']}")
        lines.append(f"Canonical example: {planning['canonical_example_path']}")
    lines.extend(["", "## Likely Code Areas"])
    lines.extend(record.files or ["(not specified in backlog entry)"])
    lines.extend(["", "## Suggested Workflow Commands"])
    workflow_commands = _workflow_commands_for_context_pack(
        task_id,
        include_archive=include_archive,
        archived=record.archived,
    )
    lines.extend(workflow_commands)
    lines.extend(["", "## Suggested Validation Commands", *_SUGGESTED_VALIDATION_COMMANDS])
    _append_pre_push_review_guidance_lines(lines, pre_push_review)
    return CommandResult(
        lines=lines,
        data={
            "task": _task_record_payload(record),
            "sprint_lines": record.sprint_lines,
            "spec_paths": record.spec_paths,
            "spec_template_path": "tasks/specs/TEMPLATE.md",
            "canonical_spec_example_path": _CANONICAL_PLANNING_EXAMPLE_PATH,
            "planning_gates": planning,
            "suggested_workflow_commands": workflow_commands,
            "suggested_validation_commands": list(_SUGGESTED_VALIDATION_COMMANDS),
            "pre_push_review_guidance": pre_push_review,
        },
    )


__all__ = [
    "_append_pre_push_review_guidance_lines",
    "_archived_task_blocked_result",
    "_planning_context",
    "_planning_marker_from_relative_path",
    "_pre_push_review_guidance",
    "_task_record_payload",
    "_workflow_commands_for_context_pack",
    "handle_context_pack",
    "handle_list_active",
    "handle_search",
    "handle_show",
]
