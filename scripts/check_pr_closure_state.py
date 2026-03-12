#!/usr/bin/env python3
# ruff: noqa: E402
"""Fail closed unless a task PR head already contains the final closure state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.horadus.python.horadus_workflow.task_repo import (
    TaskClosureState,
    clear_repo_root_override,
    normalize_task_id,
    set_repo_root_override,
    task_closure_state,
)


def _blocker_lines(closure_state: TaskClosureState) -> list[str]:
    lines: list[str] = []
    if closure_state.present_in_backlog:
        lines.append("- tasks/BACKLOG.md still contains the task as open.")
    if closure_state.present_in_active_sprint:
        lines.append("- tasks/CURRENT_SPRINT.md still lists the task under Active Tasks:")
        lines.extend(f"  {line}" for line in closure_state.active_sprint_lines)
    if not closure_state.present_in_completed:
        lines.append("- tasks/COMPLETED.md is missing the compact completion entry.")
    if not closure_state.present_in_closed_archive:
        lines.append("- archive/closed_tasks/*.md is missing the full archived task body.")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True, help="Primary task id to validate.")
    parser.add_argument("--repo-root", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        task_id = normalize_task_id(args.task_id)
    except ValueError as exc:
        print(str(exc))
        return 2

    clear_repo_root_override()
    if args.repo_root:
        override_root = Path(args.repo_root).resolve()
        set_repo_root_override(override_root)

    try:
        closure_state = task_closure_state(task_id)
    finally:
        clear_repo_root_override()
    if closure_state.ready_for_merge:
        archive_path = closure_state.closed_archive_path or "archive/closed_tasks/"
        print(
            f"closure guard passed: {task_id} is closed in live ledgers and archived ({archive_path})."
        )
        return 0

    print(f"closure guard failed: {task_id} is not fully closed on this PR head.")
    for line in _blocker_lines(closure_state):
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
