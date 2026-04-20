from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

SPEC_REFERENCE_PATTERN = re.compile(r"^\*\*Spec\*\*:\s*(?P<value>.+)$", re.MULTILINE)
BACKTICK_PATTERN = re.compile(r"`([^`]+)`")


@dataclass(frozen=True, slots=True)
class TaskSpecCandidate:
    path: str
    exists: bool
    retrieval_ready: bool
    task_id: str | None
    retrieval_kind: str | None
    retrieval_status: str | None
    canonical: bool
    supersedes: tuple[str, ...]
    superseded_by: str | None

    @property
    def active_canonical(self) -> bool:
        return (
            self.exists
            and self.retrieval_ready
            and self.canonical
            and self.retrieval_status != "superseded"
            and self.superseded_by is None
        )


@dataclass(frozen=True, slots=True)
class TaskSpecResolution:
    task_id: str
    selector: str
    candidate_paths: tuple[str, ...]
    selected_paths: tuple[str, ...]
    ambiguous: bool
    ambiguity_reason: str | None
    candidates: tuple[TaskSpecCandidate, ...]

    def paths_for_context(self) -> list[str]:
        if self.selected_paths:
            return list(self.selected_paths)
        return list(self.candidate_paths)

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "selector": self.selector,
            "candidate_paths": list(self.candidate_paths),
            "selected_paths": list(self.selected_paths),
            "ambiguous": self.ambiguous,
            "ambiguity_reason": self.ambiguity_reason,
            "candidates": [
                {
                    "path": candidate.path,
                    "exists": candidate.exists,
                    "retrieval_ready": candidate.retrieval_ready,
                    "task_id": candidate.task_id,
                    "retrieval_kind": candidate.retrieval_kind,
                    "retrieval_status": candidate.retrieval_status,
                    "canonical": candidate.canonical,
                    "supersedes": list(candidate.supersedes),
                    "superseded_by": candidate.superseded_by,
                    "active_canonical": candidate.active_canonical,
                }
                for candidate in self.candidates
            ],
        }


def spec_reference_paths_from_text(content: str) -> list[str]:
    match = SPEC_REFERENCE_PATTERN.search(content)
    if match is None:
        return []
    value = match.group("value").strip()
    if not value or value.lower() in {"none", "n/a", "not applicable"}:
        return []
    raw_values = BACKTICK_PATTERN.findall(value)
    if not raw_values:
        raw_values = [item.strip() for item in value.split(",")]
    return _dedupe_paths(_normalize_spec_reference(item) for item in raw_values)


def filename_spec_paths_for_task(repo_root: Path, task_id: str) -> list[str]:
    spec_glob = f"{task_id[5:]}-*"
    return sorted(
        str(path.relative_to(repo_root)) for path in (repo_root / "tasks" / "specs").glob(spec_glob)
    )


def resolve_task_spec_paths(
    *,
    repo_root: Path,
    task_id: str,
    raw_block: str | None = None,
) -> TaskSpecResolution:
    referenced_paths = spec_reference_paths_from_text(raw_block or "")
    selector = "backlog-spec-reference" if referenced_paths else "filename-glob"
    candidate_paths = referenced_paths or filename_spec_paths_for_task(repo_root, task_id)
    candidates = tuple(_candidate_from_path(repo_root, task_id, path) for path in candidate_paths)
    selected_paths, ambiguity_reason = _selected_paths(candidates)
    return TaskSpecResolution(
        task_id=task_id,
        selector=selector,
        candidate_paths=tuple(candidate_paths),
        selected_paths=tuple(selected_paths),
        ambiguous=ambiguity_reason is not None,
        ambiguity_reason=ambiguity_reason,
        candidates=candidates,
    )


def _selected_paths(candidates: Sequence[TaskSpecCandidate]) -> tuple[list[str], str | None]:
    if not candidates:
        return [], None
    active = _active_canonical_candidates(candidates)
    if len(active) == 1:
        return [active[0].path], None
    if len(active) > 1:
        paths = ", ".join(candidate.path for candidate in active)
        return [], f"multiple active canonical task specs remain: {paths}"
    if len(candidates) == 1:
        return [candidates[0].path], None
    paths = ", ".join(candidate.path for candidate in candidates)
    return [], f"multiple legacy task spec candidates remain: {paths}"


def _active_canonical_candidates(
    candidates: Sequence[TaskSpecCandidate],
) -> list[TaskSpecCandidate]:
    active = [candidate for candidate in candidates if candidate.active_canonical]
    superseded_paths = {
        superseded_path for candidate in active for superseded_path in candidate.supersedes
    }
    return [candidate for candidate in active if candidate.path not in superseded_paths]


def _candidate_from_path(repo_root: Path, task_id: str, relative_path: str) -> TaskSpecCandidate:
    path = repo_root / relative_path
    metadata = _front_matter(path.read_text(encoding="utf-8")) if path.exists() else {}
    retrieval = metadata.get("retrieval")
    retrieval_metadata = retrieval if isinstance(retrieval, Mapping) else {}
    metadata_task_id = _optional_str(metadata.get("task_id"))
    retrieval_kind = _optional_str(retrieval_metadata.get("kind"))
    retrieval_status = _optional_str(retrieval_metadata.get("status"))
    superseded_by = _optional_str(retrieval_metadata.get("superseded_by"))
    return TaskSpecCandidate(
        path=relative_path,
        exists=path.exists(),
        retrieval_ready=metadata_task_id == task_id and retrieval_kind == "task-spec",
        task_id=metadata_task_id,
        retrieval_kind=retrieval_kind,
        retrieval_status=retrieval_status,
        canonical=_bool_value(retrieval_metadata.get("canonical"), default=True),
        supersedes=tuple(_list_value(retrieval_metadata.get("supersedes"))),
        superseded_by=superseded_by,
    )


def _front_matter(content: str) -> dict[str, object]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        return {}
    return _parse_front_matter_lines(lines[1:closing_index])


def _parse_front_matter_lines(lines: Sequence[str]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    retrieval: dict[str, object] | None = None
    list_key: str | None = None
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            retrieval = None
            list_key = None
            key, value = _split_key_value(stripped)
            if key == "retrieval" and value == "":
                retrieval = {}
                metadata[key] = retrieval
            elif key:
                metadata[key] = _scalar_value(value)
            continue
        if retrieval is None:
            continue
        if stripped.startswith("- ") and list_key is not None:
            list_value = retrieval.setdefault(list_key, [])
            assert isinstance(list_value, list)
            list_value.append(_scalar_value(stripped[2:].strip()))
            continue
        key, value = _split_key_value(stripped)
        if not key:
            continue
        if value == "":
            retrieval[key] = []
            list_key = key
        else:
            retrieval[key] = _scalar_value(value)
            list_key = None
    return metadata


def _split_key_value(value: str) -> tuple[str, str]:
    if ":" not in value:
        return "", ""
    key, raw_value = value.split(":", 1)
    return key.strip(), raw_value.strip()


def _scalar_value(value: str) -> object:
    if value in {"", "null", "None", "~"}:
        return None
    if value in {"[]", "[ ]"}:
        return []
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
        return [item for item in items if item]
    return value.strip("'\"")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _bool_value(value: object, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _list_value(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_optional_str(item) for item in value) if item is not None]


def _normalize_spec_reference(value: str) -> str | None:
    cleaned = value.strip().strip("`'\".,;")
    if not cleaned or cleaned.lower() in {"none", "n/a", "not applicable"}:
        return None
    if cleaned.startswith("tasks/specs/") and cleaned.endswith(".md"):
        return cleaned
    if "/" not in cleaned and cleaned.endswith(".md"):
        return f"tasks/specs/{cleaned}"
    return None


def _dedupe_paths(values: Iterable[str | None]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        paths.append(value)
    return paths


__all__ = [
    "TaskSpecCandidate",
    "TaskSpecResolution",
    "filename_spec_paths_for_task",
    "resolve_task_spec_paths",
    "spec_reference_paths_from_text",
]
