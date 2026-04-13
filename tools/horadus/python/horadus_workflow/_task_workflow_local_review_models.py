from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LocalReviewContext:
    current_branch: str
    task_id: str | None
    base_branch: str
    review_target_kind: str
    review_target_value: str
    diff_text: str
    diff_stat: str
    changed_files: list[str]
    working_tree_dirty: bool


@dataclass(slots=True)
class LocalReviewParsedOutput:
    findings_reported: bool
    review_body: str


@dataclass(slots=True)
class LocalReviewProviderRun:
    provider: str
    interface_kind: str
    command: list[str]
    prompt: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    timeout_seconds: float | None = None
