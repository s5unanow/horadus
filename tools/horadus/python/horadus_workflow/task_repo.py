from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

TASK_ID_PATTERN = re.compile(r"^TASK-(\d{3})$")
SPEC_TASK_ID_PATTERN = re.compile(r"^(?P<task_num>\d{3})-[^.]+\.md$")
EXEC_PLAN_TASK_ID_PATTERN = re.compile(r"^(?P<task_id>TASK-\d{3})\.md$")
TASK_HEADER_PATTERN = re.compile(
    r"^### (?P<task_id>TASK-\d{3}): (?P<title>.+?)\n(?P<body>.*?)(?=^---\n|\Z)",
    re.MULTILINE | re.DOTALL,
)
TASK_REF_PATTERN = re.compile(r"TASK-\d{3}")
PLANNING_GATES_PATTERN = re.compile(
    r"^(?:-\s+)?(?:\*\*)?Planning Gates(?:\*\*)?:\s*(?P<value>.+)$",
    re.MULTILINE,
)
EXEC_PLAN_LINE_PATTERN = re.compile(r"^\*\*Exec Plan\*\*:\s*(?P<value>.+)$", re.MULTILINE)
TASK_STATUS_ORDER = {"active": 0, "backlog": 1, "completed": 2}
COMPLETED_TASK_LINE_PATTERN = re.compile(r"^-\s+(TASK-\d{3}):\s+(.+?)\s+✅(?:\s|$)")
CLOSED_TASK_ARCHIVE_GUIDANCE = (
    "Do not read `archive/closed_tasks/` during normal implementation flow unless "
    "a user explicitly asks for historical context or an archive-aware CLI flag is used."
)
_REPO_ROOT_ENV = "HORADUS_REPO_ROOT"
_REPO_ROOT_OVERRIDE: Path | None = None


@dataclass(slots=True)
class ActiveTask:
    task_id: str
    title: str
    requires_human: bool
    note: str | None
    raw_line: str


@dataclass(slots=True)
class BlockerMetadata:
    task_id: str
    owner: str
    last_touched: str
    next_action: str
    escalate_after_days: int
    raw_line: str
    urgency: BlockerUrgency | None = None


@dataclass(slots=True)
class BlockerUrgency:
    state: str
    as_of: str
    days_until_next_action: int | None
    is_overdue: bool
    is_due_today: bool
    days_since_last_touched: int | None
    escalation_due_date: str | None
    days_until_escalation: int | None
    is_escalated: bool


@dataclass(slots=True)
class SearchHit:
    source: str
    line_number: int
    line: str


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    title: str
    priority: str | None
    estimate: str | None
    description: list[str]
    files: list[str]
    acceptance_criteria: list[str]
    assessment_refs: list[str]
    raw_block: str
    status: str
    sprint_lines: list[str]
    spec_paths: list[str]
    source_path: str = ""
    archived: bool = False


@dataclass(slots=True)
class TaskClosureState:
    task_id: str
    present_in_backlog: bool
    active_sprint_lines: list[str]
    present_in_completed: bool
    present_in_closed_archive: bool
    closed_archive_path: str | None

    @property
    def present_in_active_sprint(self) -> bool:
        return bool(self.active_sprint_lines)

    @property
    def ready_for_merge(self) -> bool:
        return (
            not self.present_in_backlog
            and not self.present_in_active_sprint
            and self.present_in_completed
            and self.present_in_closed_archive
        )


def set_repo_root_override(path: Path | None) -> None:
    global _REPO_ROOT_OVERRIDE
    _REPO_ROOT_OVERRIDE = path.resolve() if path is not None else None


def clear_repo_root_override() -> None:
    set_repo_root_override(None)


def _looks_like_repo_root(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "tasks").exists()


def _discover_repo_root() -> Path:
    if _REPO_ROOT_OVERRIDE is not None:
        return _REPO_ROOT_OVERRIDE
    env_root = os.getenv(_REPO_ROOT_ENV)
    if env_root:
        return Path(env_root).resolve()

    search_starts = (Path(__file__).resolve(), Path.cwd().resolve())
    for start in search_starts:
        current = start if start.is_dir() else start.parent
        for candidate in (current, *current.parents):
            if _looks_like_repo_root(candidate):
                return candidate
    msg = "Unable to locate Horadus repo root from workflow tooling package."
    raise RuntimeError(msg)


def repo_root() -> Path:
    return _discover_repo_root()


def backlog_path() -> Path:
    return repo_root() / "tasks" / "BACKLOG.md"


def current_sprint_path() -> Path:
    return repo_root() / "tasks" / "CURRENT_SPRINT.md"


def completed_path() -> Path:
    return repo_root() / "tasks" / "COMPLETED.md"


def archive_root() -> Path:
    return repo_root() / "archive"


def closed_tasks_archive_dir() -> Path:
    return archive_root() / "closed_tasks"


def archive_quarter_label(at_date: date | None = None) -> str:
    selected_date = at_date or current_date()
    quarter = ((selected_date.month - 1) // 3) + 1
    return f"{selected_date.year}-Q{quarter}"


def closed_tasks_archive_path(at_date: date | None = None) -> Path:
    return closed_tasks_archive_dir() / f"{archive_quarter_label(at_date)}.md"


def closed_tasks_archive_paths() -> list[Path]:
    archive_dir = closed_tasks_archive_dir()
    if not archive_dir.exists():
        return []
    return sorted(archive_dir.glob("*.md"), reverse=True)


def archived_task_paths() -> list[Path]:
    snapshot_paths = archive_backlog_paths()
    closed_task_paths = closed_tasks_archive_paths()
    return [*closed_task_paths, *snapshot_paths]


def archive_backlog_paths() -> list[Path]:
    archive_dir = archive_root()
    if not archive_dir.exists():
        return []
    return sorted(archive_dir.glob("*/tasks/BACKLOG.md"), reverse=True)


def normalize_task_id(value: str) -> str:
    normalized = value.strip().upper()
    if normalized.isdigit() and len(normalized) == 3:
        normalized = f"TASK-{normalized}"
    if not TASK_ID_PATTERN.match(normalized):
        raise ValueError(f"Invalid task id '{value}'. Expected TASK-XXX or XXX.")
    return normalized


def slugify_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower())
    slug = slug.strip("-")
    if not slug:
        raise ValueError(f"Invalid branch suffix '{value}'.")
    return slug


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def current_date() -> date:
    return datetime.now(tz=UTC).date()


def active_section_text(path: Path | None = None) -> str:
    sprint_path = path or current_sprint_path()
    text = read_text(sprint_path)
    match = re.search(r"^## Active Tasks\n(?P<body>.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError(f"Unable to locate Active Tasks section in {sprint_path}")
    return match.group("body").strip("\n")


def human_blocker_section_text(path: Path | None = None) -> str:
    sprint_path = path or current_sprint_path()
    text = read_text(sprint_path)
    match = re.search(
        r"^## Human Blocker Metadata\n(?P<body>.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        return ""
    return match.group("body").strip("\n")


def parse_active_tasks(path: Path | None = None) -> list[ActiveTask]:
    section = active_section_text(path)
    tasks: list[ActiveTask] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        match = TASK_REF_PATTERN.search(line)
        if match is None:
            continue
        task_id = match.group(0)
        line_without_bullet = re.sub(r"^-\s*", "", line)
        line_without_id = line_without_bullet.replace(f"`{task_id}`", "", 1).strip()
        note = None
        if "—" in line_without_id:
            title_text, note = [part.strip() for part in line_without_id.split("—", 1)]
        else:
            title_text = line_without_id
        requires_human = "[REQUIRES_HUMAN]" in title_text
        title = (
            title_text.replace("`[REQUIRES_HUMAN]`", "")
            .replace("[REQUIRES_HUMAN]", "")
            .strip(" -`")
        )
        tasks.append(
            ActiveTask(
                task_id=task_id,
                title=title,
                requires_human=requires_human,
                note=note,
                raw_line=line,
            )
        )
    return tasks


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def blocker_urgency(
    *,
    last_touched: str,
    next_action: str,
    escalate_after_days: int,
    as_of: date | None = None,
) -> BlockerUrgency:
    evaluation_date = as_of or current_date()
    next_action_date = _parse_iso_date(next_action)
    last_touched_date = _parse_iso_date(last_touched)

    days_until_next_action = None
    is_overdue = False
    is_due_today = False
    if next_action_date is not None:
        days_until_next_action = (next_action_date - evaluation_date).days
        is_overdue = days_until_next_action < 0
        is_due_today = days_until_next_action == 0

    days_since_last_touched = None
    escalation_due_date = None
    days_until_escalation = None
    is_escalated = False
    if last_touched_date is not None and escalate_after_days > 0:
        days_since_last_touched = (evaluation_date - last_touched_date).days
        escalation_date = last_touched_date + timedelta(days=escalate_after_days)
        escalation_due_date = escalation_date.isoformat()
        days_until_escalation = (escalation_date - evaluation_date).days
        is_escalated = days_until_escalation < 0

    if is_overdue:
        state = "overdue"
    elif is_due_today:
        state = "due_today"
    else:
        state = "pending"

    return BlockerUrgency(
        state=state,
        as_of=evaluation_date.isoformat(),
        days_until_next_action=days_until_next_action,
        is_overdue=is_overdue,
        is_due_today=is_due_today,
        days_since_last_touched=days_since_last_touched,
        escalation_due_date=escalation_due_date,
        days_until_escalation=days_until_escalation,
        is_escalated=is_escalated,
    )


def parse_human_blockers(
    path: Path | None = None,
    *,
    as_of: date | None = None,
    task_ids: set[str] | None = None,
) -> list[BlockerMetadata]:
    section = human_blocker_section_text(path)
    blockers: list[BlockerMetadata] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        parts = [part.strip() for part in line[2:].split("|")]
        if len(parts) != 5:
            continue
        task_id = parts[0]
        if task_ids is not None and task_id not in task_ids:
            continue
        metadata: dict[str, str] = {}
        for chunk in parts[1:]:
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            metadata[key.strip()] = value.strip()
        escalate_raw = metadata.get("escalate_after_days", "0")
        try:
            escalate_days = int(escalate_raw)
        except ValueError:
            escalate_days = 0
        blockers.append(
            BlockerMetadata(
                task_id=task_id,
                owner=metadata.get("owner", ""),
                last_touched=metadata.get("last_touched", ""),
                next_action=metadata.get("next_action", ""),
                escalate_after_days=escalate_days,
                raw_line=line,
                urgency=blocker_urgency(
                    last_touched=metadata.get("last_touched", ""),
                    next_action=metadata.get("next_action", ""),
                    escalate_after_days=escalate_days,
                    as_of=as_of,
                ),
            )
        )
    return blockers


def _parse_task_block(task_id: str, title: str, raw_block: str) -> TaskRecord:
    lines = raw_block.splitlines()
    priority = None
    estimate = None
    description: list[str] = []
    files: list[str] = []
    acceptance: list[str] = []
    assessment_refs: list[str] = []

    in_description = False
    in_assessment_refs = False
    in_acceptance = False

    for raw_line in lines[1:]:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("**Priority**:"):
            priority = stripped.split(":", 1)[1].strip()
            in_description = True
            in_assessment_refs = False
            in_acceptance = False
            continue
        if stripped.startswith("**Estimate**:"):
            estimate = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("**Assessment-Ref**:"):
            in_assessment_refs = True
            in_acceptance = False
            continue
        if stripped.startswith("**Files**:"):
            files = [item.strip() for item in stripped.split(":", 1)[1].split(",") if item.strip()]
            in_assessment_refs = False
            in_acceptance = False
            continue
        if stripped.startswith("**Acceptance Criteria**:"):
            in_acceptance = True
            in_assessment_refs = False
            continue
        if stripped.startswith("**") and ":" in stripped:
            in_assessment_refs = False
            in_acceptance = False
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            in_description = False
            in_assessment_refs = False
            in_acceptance = False
            continue
        if in_assessment_refs and stripped.startswith("- "):
            assessment_refs.append(stripped[2:].strip())
            continue
        if in_acceptance and stripped.startswith("- ["):
            acceptance.append(stripped)
            continue
        if in_description and stripped:
            description.append(stripped)

    return TaskRecord(
        task_id=task_id,
        title=title,
        priority=priority,
        estimate=estimate,
        description=description,
        files=files,
        acceptance_criteria=acceptance,
        assessment_refs=assessment_refs,
        raw_block=raw_block.strip(),
        status="backlog",
        sprint_lines=[],
        spec_paths=[],
        source_path=str(backlog_path().relative_to(repo_root())),
    )


def backlog_task_records(path: Path | None = None) -> dict[str, TaskRecord]:
    records: dict[str, TaskRecord] = {}
    selected_path = path or backlog_path()
    backlog_text = read_text(selected_path)
    for match in TASK_HEADER_PATTERN.finditer(backlog_text):
        task_id = match.group("task_id")
        title = match.group("title").strip()
        raw_block = match.group(0)
        record = _parse_task_block(task_id, title, raw_block)
        record.source_path = str(selected_path.relative_to(repo_root()))
        record.archived = selected_path != backlog_path()
        records[task_id] = record
    return records


def task_block_match(task_id: str, path: Path | None = None) -> re.Match[str] | None:
    normalized = normalize_task_id(task_id)
    selected_path = path or backlog_path()
    for match in TASK_HEADER_PATTERN.finditer(read_text(selected_path)):
        if match.group("task_id") == normalized:
            return match
    return None


def sprint_lines_for_task(task_id: str, path: Path | None = None) -> list[str]:
    sprint_text = read_text(path or current_sprint_path())
    return [line for line in sprint_text.splitlines() if task_id in line]


def spec_paths_for_task(task_id: str) -> list[str]:
    spec_glob = f"{task_id[5:]}-*"
    return sorted(
        str(path.relative_to(repo_root()))
        for path in (repo_root() / "tasks" / "specs").glob(spec_glob)
    )


def exec_plan_paths_for_task(task_id: str) -> list[str]:
    candidate = repo_root() / "tasks" / "exec_plans" / f"{task_id}.md"
    if not candidate.exists():
        return []
    return [str(candidate.relative_to(repo_root()))]


def planning_gates_value_from_text(content: str) -> str | None:
    match = PLANNING_GATES_PATTERN.search(content)
    if match is None:
        return None
    value = match.group("value").strip()
    return value or None


def planning_gates_required(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lstrip("`*_ ").lower()
    if normalized.startswith("required"):
        return True
    if normalized.startswith("not required"):
        return False
    return None


def task_planning_gates_value(record: TaskRecord) -> str | None:
    return planning_gates_value_from_text(record.raw_block)


def task_requires_exec_plan(record: TaskRecord) -> bool:
    match = EXEC_PLAN_LINE_PATTERN.search(record.raw_block)
    if match is None:
        return False
    return match.group("value").strip().lower().startswith("required")


def task_id_from_spec_path(relative_path: str) -> str | None:
    match = SPEC_TASK_ID_PATTERN.match(Path(relative_path).name)
    if match is None:
        return None
    return f"TASK-{match.group('task_num')}"


def task_id_from_exec_plan_path(relative_path: str) -> str | None:
    match = EXEC_PLAN_TASK_ID_PATTERN.match(Path(relative_path).name)
    if match is None:
        return None
    return match.group("task_id")


def completed_task_ids(path: Path | None = None) -> set[str]:
    selected_path = path or completed_path()
    if not selected_path.exists():
        return set()
    task_ids: set[str] = set()
    for line in read_text(selected_path).splitlines():
        match = COMPLETED_TASK_LINE_PATTERN.match(line.strip())
        if match is not None:
            task_ids.add(match.group(1))
    return task_ids


def is_task_completed(task_id: str) -> bool:
    return task_id in completed_task_ids()


def archived_task_records() -> dict[str, TaskRecord]:
    records: dict[str, TaskRecord] = {}
    for path in archived_task_paths():
        for task_id, record in backlog_task_records(path).items():
            records.setdefault(task_id, record)
    return records


def archived_task_record(task_id: str) -> TaskRecord | None:
    normalized = normalize_task_id(task_id)
    return archived_task_records().get(normalized)


def closed_task_archive_record(task_id: str) -> TaskRecord | None:
    normalized = normalize_task_id(task_id)
    for path in closed_tasks_archive_paths():
        record = backlog_task_records(path).get(normalized)
        if record is not None:
            return record
    return None


def task_closure_state(task_id: str) -> TaskClosureState:
    normalized = normalize_task_id(task_id)
    active_lines = [task.raw_line for task in parse_active_tasks() if task.task_id == normalized]
    closed_archive_record = closed_task_archive_record(normalized)
    return TaskClosureState(
        task_id=normalized,
        present_in_backlog=task_block_match(normalized) is not None,
        active_sprint_lines=active_lines,
        present_in_completed=normalized in completed_task_ids(),
        present_in_closed_archive=closed_archive_record is not None,
        closed_archive_path=(
            closed_archive_record.source_path if closed_archive_record is not None else None
        ),
    )


def _enrich_task_record(record: TaskRecord) -> TaskRecord:
    enriched = replace(
        record,
        description=list(record.description),
        files=list(record.files),
        acceptance_criteria=list(record.acceptance_criteria),
        assessment_refs=list(record.assessment_refs),
        sprint_lines=[],
        spec_paths=[],
    )
    normalized = enriched.task_id
    enriched.sprint_lines = sprint_lines_for_task(normalized)
    enriched.spec_paths = spec_paths_for_task(normalized)
    if is_task_completed(normalized):
        enriched.status = "completed"
    elif enriched.sprint_lines:
        enriched.status = "active"
    else:
        enriched.status = "backlog"
    return enriched


def task_record(task_id: str, *, include_archive: bool = False) -> TaskRecord | None:
    normalized = normalize_task_id(task_id)
    record = backlog_task_records().get(normalized)
    if record is None and include_archive:
        record = archived_task_record(normalized)
    if record is None:
        return None
    return _enrich_task_record(record)


def search_task_records(
    query: str,
    *,
    status: str = "all",
    limit: int | None = None,
    include_archive: bool = False,
) -> list[TaskRecord]:
    normalized = query.strip().lower()
    matches: list[TaskRecord] = []
    records = backlog_task_records()
    if include_archive:
        for task_id, record in archived_task_records().items():
            records.setdefault(task_id, record)
    for record in records.values():
        haystack = "\n".join(
            [
                record.task_id,
                record.title,
                "\n".join(record.description),
                "\n".join(record.files),
                "\n".join(record.acceptance_criteria),
            ]
        ).lower()
        if normalized in haystack:
            enriched = _enrich_task_record(record)
            if status == "all" or enriched.status == status:
                matches.append(enriched)
    matches.sort(
        key=lambda record: (
            TASK_STATUS_ORDER.get(record.status, 99),
            int(record.task_id[5:]),
        )
    )
    if limit is not None:
        return matches[:limit]
    return matches


def line_search(path: Path, pattern: str) -> list[SearchHit]:
    regex = re.compile(pattern, re.IGNORECASE)
    hits: list[SearchHit] = []
    for index, line in enumerate(read_text(path).splitlines(), start=1):
        if regex.search(line):
            hits.append(
                SearchHit(
                    source=str(path.relative_to(repo_root())),
                    line_number=index,
                    line=line,
                )
            )
    return hits
