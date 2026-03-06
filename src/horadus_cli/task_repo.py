from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TASK_ID_PATTERN = re.compile(r"^TASK-(\d{3})$")
TASK_HEADER_PATTERN = re.compile(
    r"^### (?P<task_id>TASK-\d{3}): (?P<title>.+?)\n(?P<body>.*?)(?=^---\n|\Z)",
    re.MULTILINE | re.DOTALL,
)
TASK_REF_PATTERN = re.compile(r"TASK-\d{3}")
TASK_STATUS_ORDER = {"active": 0, "backlog": 1, "completed": 2}


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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def backlog_path() -> Path:
    return repo_root() / "tasks" / "BACKLOG.md"


def current_sprint_path() -> Path:
    return repo_root() / "tasks" / "CURRENT_SPRINT.md"


def completed_path() -> Path:
    return repo_root() / "tasks" / "COMPLETED.md"


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


def parse_human_blockers(path: Path | None = None) -> list[BlockerMetadata]:
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
    )


def backlog_task_records() -> dict[str, TaskRecord]:
    records: dict[str, TaskRecord] = {}
    backlog_text = read_text(backlog_path())
    for match in TASK_HEADER_PATTERN.finditer(backlog_text):
        task_id = match.group("task_id")
        title = match.group("title").strip()
        raw_block = match.group(0)
        records[task_id] = _parse_task_block(task_id, title, raw_block)
    return records


def sprint_lines_for_task(task_id: str, path: Path | None = None) -> list[str]:
    sprint_text = read_text(path or current_sprint_path())
    return [line for line in sprint_text.splitlines() if task_id in line]


def spec_paths_for_task(task_id: str) -> list[str]:
    spec_glob = f"{task_id[5:]}-*"
    return sorted(
        str(path.relative_to(repo_root()))
        for path in (repo_root() / "tasks" / "specs").glob(spec_glob)
    )


def is_task_completed(task_id: str) -> bool:
    completed_text = read_text(completed_path())
    return task_id in completed_text


def task_record(task_id: str) -> TaskRecord | None:
    normalized = normalize_task_id(task_id)
    record = backlog_task_records().get(normalized)
    if record is None:
        return None
    record.sprint_lines = sprint_lines_for_task(normalized)
    record.spec_paths = spec_paths_for_task(normalized)
    if is_task_completed(normalized):
        record.status = "completed"
    elif record.sprint_lines:
        record.status = "active"
    return record


def search_task_records(
    query: str,
    *,
    status: str = "all",
    limit: int | None = None,
) -> list[TaskRecord]:
    normalized = query.strip().lower()
    matches: list[TaskRecord] = []
    for record in backlog_task_records().values():
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
            enriched = task_record(record.task_id)
            if enriched is not None and (status == "all" or enriched.status == status):
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
