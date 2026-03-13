from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from ._docs_freshness_models import _Override

_TASK_ID_PATTERN = re.compile(r"\bTASK-(\d{3})\b")
_CURRENT_SPRINT_ACTIVE_HEADING = "Active Tasks"
_HUMAN_BLOCKER_METADATA_HEADING = "Human Blocker Metadata"
_TELEGRAM_SCOPE_HEADING = "Telegram Launch Scope"


def _load_overrides(override_path: Path) -> tuple[_Override, ...]:
    if not override_path.exists():
        return ()
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    raw_overrides = payload.get("overrides", [])
    if not isinstance(raw_overrides, list):
        msg = f"Override file '{override_path}' must contain an 'overrides' list"
        raise ValueError(msg)

    loaded: list[_Override] = []
    for row in raw_overrides:
        if not isinstance(row, dict):
            msg = f"Override row in '{override_path}' is not an object"
            raise ValueError(msg)
        rule_id = str(row.get("rule_id", "")).strip()
        path = str(row.get("path", "")).strip()
        reason = str(row.get("reason", "")).strip()
        expires_on_raw = str(row.get("expires_on", "")).strip()
        if not rule_id or not path or not reason or not expires_on_raw:
            msg = f"Override row in '{override_path}' is missing required fields"
            raise ValueError(msg)
        loaded.append(
            _Override(
                rule_id=rule_id,
                path=path,
                reason=reason,
                expires_on=date.fromisoformat(expires_on_raw),
            )
        )
    return tuple(loaded)


def _parse_marker_date(content: str, label: str) -> date | None:
    pattern = re.compile(rf"\*\*{re.escape(label)}\*\*:\s*(\d{{4}}-\d{{2}}-\d{{2}})")
    match = pattern.search(content)
    if match is None:
        return None
    return date.fromisoformat(match.group(1))


def _extract_h2_section(content: str, heading: str) -> str | None:
    heading_pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = heading_pattern.search(content)
    if match is None:
        return None

    section_start = match.end()
    remainder = content[section_start:]
    next_heading_match = re.search(r"^##\s+.+$", remainder, re.MULTILINE)
    if next_heading_match is None:
        return remainder

    section_end = section_start + next_heading_match.start()
    return content[section_start:section_end]


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _extract_task_ids(content: str) -> set[str]:
    return {f"TASK-{match.group(1)}" for match in _TASK_ID_PATTERN.finditer(content)}


def _extract_section_task_ids(content: str, heading: str) -> set[str]:
    section = _extract_h2_section(content, heading)
    if section is None:
        return set()
    return _extract_task_ids(section)


def _extract_current_sprint_active_tasks(content: str) -> tuple[set[str], set[str]]:
    section = _extract_h2_section(content, _CURRENT_SPRINT_ACTIVE_HEADING)
    if section is None:
        return set(), set()

    active_tasks: set[str] = set()
    active_requires_human_tasks: set[str] = set()
    for line in section.splitlines():
        line_task_ids = _extract_task_ids(line)
        if not line_task_ids:
            continue
        active_tasks.update(line_task_ids)
        if "[REQUIRES_HUMAN]" in line:
            active_requires_human_tasks.update(line_task_ids)

    return active_tasks, active_requires_human_tasks


def _extract_human_blocker_metadata(content: str) -> dict[str, dict[str, str]]:
    section = _extract_h2_section(content, _HUMAN_BLOCKER_METADATA_HEADING)
    if section is None:
        return {}

    metadata: dict[str, dict[str, str]] = {}
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        task_ids = _extract_task_ids(line)
        if not task_ids:
            continue
        fields: dict[str, str] = {}
        for segment in line.split("|"):
            key, separator, value = segment.partition("=")
            if separator != "=":
                continue
            normalized_key = key.strip().lstrip("-").strip().lower()
            if not normalized_key:
                continue
            fields[normalized_key] = value.strip()
        for task_id in task_ids:
            metadata[task_id] = fields
    return metadata


def _extract_telegram_launch_scope(content: str) -> str | None:
    section = _extract_h2_section(content, _TELEGRAM_SCOPE_HEADING)
    if section is None:
        return None

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if "launch_scope" not in line:
            continue
        _, _, value = line.partition(":")
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _extract_completed_task_ids(content: str) -> set[str]:
    completed: set[str] = set()
    for line in content.splitlines():
        if not line.lstrip().startswith("-"):
            continue
        completed.update(_extract_task_ids(line))
    return completed
