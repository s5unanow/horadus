from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from tools.horadus.python.horadus_workflow import task_repo

REVIEW_GATE_STATE_PATH_ENV = "HORADUS_REVIEW_GATE_STATE_PATH"


def _parse_github_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _git_metadata_dir() -> Path:
    dot_git_path = task_repo.repo_root() / ".git"
    if dot_git_path.is_dir():
        return dot_git_path
    if dot_git_path.is_file():
        gitdir_line = dot_git_path.read_text().strip()
        prefix = "gitdir:"
        if gitdir_line.startswith(prefix):
            return (dot_git_path.parent / gitdir_line[len(prefix) :].strip()).resolve()
    return dot_git_path


def _review_gate_state_path() -> Path:
    override = os.environ.get(REVIEW_GATE_STATE_PATH_ENV)
    if override:
        return Path(override)
    return _git_metadata_dir() / "horadus" / "review_gate_windows.json"


def _review_gate_state_key(*, repo: str, pr_number: int, reviewer_login: str) -> str:
    return f"{repo}#{pr_number}#{reviewer_login}"


def persisted_wait_window_started_at(
    *,
    repo: str,
    pr_number: int,
    reviewer_login: str,
    head_oid: str,
    now: datetime,
) -> datetime:
    state_path = _review_gate_state_path()
    payload: object = {}
    try:
        if state_path.exists():
            payload = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        payload = {}
    state = payload if isinstance(payload, dict) else {}

    key = _review_gate_state_key(repo=repo, pr_number=pr_number, reviewer_login=reviewer_login)
    started_at = now
    entry = state.get(key)
    if isinstance(entry, dict) and str(entry.get("head_oid") or "").strip() == head_oid:
        persisted_started_at = _parse_github_timestamp(entry.get("started_at"))
        if persisted_started_at is not None:
            started_at = min(persisted_started_at, now)
    state[key] = {"head_oid": head_oid, "started_at": started_at.isoformat()}
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
    except OSError:
        return started_at
    return started_at


def start_wait_window(*, repo: str, pr_number: int, reviewer_login: str, head_oid: str) -> datetime:
    return persisted_wait_window_started_at(
        repo=repo,
        pr_number=pr_number,
        reviewer_login=reviewer_login,
        head_oid=head_oid,
        now=datetime.now(tz=UTC),
    )
