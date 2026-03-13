from __future__ import annotations

import json

from tools.horadus.python.horadus_workflow import task_repo
from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _ensure_required_hooks() -> tuple[bool, list[str]]:
    repo_root = shared._compat_attr("repo_root", task_repo)
    hooks_dir = repo_root() / ".git" / "hooks"
    required = ("pre-commit", "pre-push", "commit-msg")
    missing: list[str] = []
    for hook_name in required:
        hook_path = hooks_dir / hook_name
        if (
            not hook_path.exists()
            or not hook_path.is_file()
            or not hook_path.stat().st_mode & 0o111
        ):
            missing.append(hook_name)
    return (not missing, missing)


def _open_task_prs() -> tuple[bool, list[str] | str]:
    result = shared._run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--base",
            "main",
            "--author",
            "@me",
            "--search",
            "head:codex/task-",
            "--limit",
            "100",
            "--json",
            "number,headRefName,url",
        ]
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        return (False, message)
    payload = json.loads(result.stdout or "[]")
    open_prs = [
        f"#{entry['number']} {entry['headRefName']} {entry['url']}"
        for entry in payload
        if str(entry.get("headRefName", "")).startswith("codex/task-")
    ]
    return (True, open_prs)


__all__ = [
    "_ensure_required_hooks",
    "_open_task_prs",
]
