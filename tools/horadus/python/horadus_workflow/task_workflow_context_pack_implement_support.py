from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from tools.horadus.python.horadus_workflow import task_repo

_MARKER_PATTERN_TEMPLATE = r"^\*\*{label}\*\*:\s*(?P<value>.+)$"
_SECTION_PATTERN_TEMPLATE = r"^##\s+{heading}\s*\n(?P<body>.*?)(?=^##\s+|\Z)"
_TRAILING_QUALIFIER_PATTERN = re.compile(r"\s+\([^)]*\)\s*$")
_DECLARED_TEST_PREFIX = "tests/"
_WORKFLOW_PREFIX = "tools/horadus/python/horadus_workflow/"
_CLI_PREFIX = "tools/horadus/python/horadus_cli/"
_TASK_LEDGER_PATHS = {
    "tasks/CURRENT_SPRINT.md": (
        ("tests/horadus_cli/v2/test_task_query.py", "task_ledger_doc"),
        ("tests/horadus_cli/v2/test_task_repo.py", "task_ledger_doc"),
        ("tests/horadus_cli/v2/test_task_ledgers.py", "task_ledger_doc"),
        ("tests/workflow/test_docs_freshness.py", "task_ledger_doc"),
    )
}
_ORIENTATION_DOCS = (
    (
        "tasks/CURRENT_SPRINT.md",
        "current-sprint",
        "Sprint goal, active task lines, blocker metadata, and sprint-scope constraints.",
        "Use before implementation to confirm task status, sequencing, and live constraints.",
    ),
    (
        "docs/ARCHITECTURE.md",
        "architecture",
        "System context plus ingestion, processing, worker, and storage flow boundaries.",
        "Use when a change touches runtime boundaries, orchestration, or service interactions.",
    ),
    (
        "docs/DATA_MODEL.md",
        "data-model",
        "Authoritative ERD and table inventory for runtime persistence behavior.",
        "Use when a change touches storage, schema assumptions, or model semantics.",
    ),
)


@dataclass(frozen=True, slots=True)
class OrientationDoc:
    path: str
    kind: str
    summary: str
    use_when: str


@dataclass(frozen=True, slots=True)
class DerivedTestCandidate:
    path: str
    source_path: str
    match_reason: str


def normalize_declared_path(raw_path: str) -> str:
    normalized = raw_path.strip().replace("`", "").strip()
    normalized = _TRAILING_QUALIFIER_PATTERN.sub("", normalized)
    return normalized.rstrip(".,;: ")


def normalized_declared_paths(raw_paths: Sequence[str]) -> list[str]:
    normalized_paths: list[str] = []
    for raw_path in raw_paths:
        normalized = normalize_declared_path(raw_path)
        if normalized:
            normalized_paths.append(normalized)
    return normalized_paths


def task_autonomous_eligible(*, title: object, sprint_lines: Sequence[str]) -> bool:
    title_text = str(title or "")
    return "[REQUIRES_HUMAN]" not in title_text and all(
        "[REQUIRES_HUMAN]" not in line for line in sprint_lines
    )


def implement_mode_orientation_documents() -> tuple[OrientationDoc, ...]:
    return tuple(OrientationDoc(*row) for row in _ORIENTATION_DOCS)


def current_sprint_extract(task_id: str) -> dict[str, object]:
    sprint_path = task_repo.current_sprint_path()
    if not sprint_path.exists():
        return {
            "path": "tasks/CURRENT_SPRINT.md",
            "sprint_number": None,
            "sprint_goal": None,
            "sprint_dates": None,
            "active_task_lines": [],
            "selection_note_lines": [],
            "suggested_sequence_lines": [],
            "applicable_blockers": [],
            "constraints": [],
        }

    sprint_text = task_repo.read_text(sprint_path)
    return {
        "path": str(sprint_path.relative_to(task_repo.repo_root())),
        "sprint_number": _marker_value(sprint_text, "Sprint Number"),
        "sprint_goal": _marker_value(sprint_text, "Sprint Goal"),
        "sprint_dates": _marker_value(sprint_text, "Sprint Dates"),
        "active_task_lines": _matching_section_lines(sprint_text, "Active Tasks", task_id),
        "selection_note_lines": _matching_section_lines(sprint_text, "Selection Notes", task_id),
        "suggested_sequence_lines": _matching_section_lines(
            sprint_text, "Suggested Sequence", task_id
        ),
        "applicable_blockers": [
            asdict(blocker) for blocker in task_repo.parse_human_blockers(task_ids={task_id})
        ],
        "constraints": _current_sprint_constraints(sprint_text),
    }


def derive_test_candidates(*, declared_paths: Sequence[str]) -> list[dict[str, object]]:
    repo_root = task_repo.repo_root()
    candidates: list[DerivedTestCandidate] = []
    seen: set[tuple[str, str, str]] = set()

    def add_candidate(path: str, source_path: str, match_reason: str) -> None:
        candidate = path.rstrip("/")
        repo_candidate = repo_root / candidate
        if not repo_candidate.exists():
            return
        key = (candidate, source_path, match_reason)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            DerivedTestCandidate(
                path=candidate,
                source_path=source_path,
                match_reason=match_reason,
            )
        )

    for declared_path in declared_paths:
        if declared_path.startswith(_DECLARED_TEST_PREFIX):
            add_candidate(declared_path, declared_path, "declared_test_path")
        if declared_path.startswith(_WORKFLOW_PREFIX):
            add_candidate("tests/workflow", declared_path, "workflow_helper_path")
            add_candidate("tests/horadus_cli/v2", declared_path, "workflow_cli_surface")
        if declared_path.startswith(_CLI_PREFIX):
            add_candidate("tests/horadus_cli/v2", declared_path, "cli_surface_path")
        if declared_path.startswith("src/"):
            area = declared_path[len("src/") :].split("/", 1)[0]
            if area:
                add_candidate(f"tests/{area}", declared_path, "runtime_surface_path")
        for candidate_path, reason in _TASK_LEDGER_PATHS.get(declared_path, ()):
            add_candidate(candidate_path, declared_path, reason)
        if declared_path.endswith(".py"):
            for candidate_path, reason in _module_stem_test_candidates(declared_path):
                add_candidate(candidate_path, declared_path, reason)

    return [asdict(candidate) for candidate in candidates]


def derived_task_status(task_payload: Mapping[str, object]) -> str | None:
    status = task_payload.get("status")
    if status is None:
        return None
    return str(status)


def included_sources_for_implement_mode(
    *,
    task_payload: Mapping[str, object],
    sprint_lines: Sequence[str],
    spec_paths: Sequence[str],
    planning: Mapping[str, object],
) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = [
        {
            "path": task_payload.get("source_path") or task_payload.get("backlog_path"),
            "reason": "primary task definition",
        },
        {
            "path": task_payload.get("current_sprint_path"),
            "reason": "task-scoped sprint membership lines",
            "lines": list(sprint_lines),
        },
    ]
    sources.extend(
        {"path": spec_path, "reason": "matching task spec candidate"} for spec_path in spec_paths
    )
    authoritative_artifact = planning.get("authoritative_artifact_path")
    if authoritative_artifact is not None:
        sources.append(
            {
                "path": authoritative_artifact,
                "reason": "authoritative planning artifact",
            }
        )
    for document in implement_mode_orientation_documents():
        if document.path == task_payload.get("current_sprint_path"):
            continue
        sources.append(
            {
                "path": document.path,
                "reason": "compact orientation metadata",
            }
        )
    deduped_sources: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for source in sources:
        path = source.get("path")
        normalized_path = None if path is None else str(path)
        if normalized_path is None or normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        deduped_sources.append(source)
    return deduped_sources


def _current_sprint_constraints(sprint_text: str) -> list[dict[str, object]]:
    constraints: list[dict[str, object]] = []
    for heading, match_reason in (("Telegram Launch Scope", "repo_launch_scope"),):
        lines = _section_lines(sprint_text, heading)
        if lines:
            constraints.append(
                {
                    "section": heading,
                    "lines": lines,
                    "match_reason": match_reason,
                }
            )
    return constraints


def _module_stem_test_candidates(declared_path: str) -> list[tuple[str, str]]:
    stem = Path(declared_path).stem
    stems = {stem}
    if stem.startswith("task_workflow_"):
        stems.add(stem.replace("task_workflow_", "task_", 1))
    return [
        (f"tests/horadus_cli/v2/test_{candidate_stem}.py", "module_stem_match")
        for candidate_stem in sorted(stems)
    ] + [
        (f"tests/workflow/test_{candidate_stem}.py", "module_stem_match")
        for candidate_stem in sorted(stems)
    ]


def _marker_value(content: str, label: str) -> str | None:
    pattern = re.compile(_MARKER_PATTERN_TEMPLATE.format(label=re.escape(label)), re.MULTILINE)
    match = pattern.search(content)
    if match is None:
        return None
    value = match.group("value").strip()
    return value or None


def _matching_section_lines(content: str, heading: str, task_id: str) -> list[str]:
    return [line for line in _section_lines(content, heading) if task_id in line]


def _section_lines(content: str, heading: str) -> list[str]:
    pattern = re.compile(
        _SECTION_PATTERN_TEMPLATE.format(heading=re.escape(heading)),
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        return []
    return [line for line in match.group("body").splitlines() if line.strip()]


__all__ = [
    "OrientationDoc",
    "current_sprint_extract",
    "derive_test_candidates",
    "derived_task_status",
    "implement_mode_orientation_documents",
    "included_sources_for_implement_mode",
    "normalize_declared_path",
    "normalized_declared_paths",
    "task_autonomous_eligible",
]
