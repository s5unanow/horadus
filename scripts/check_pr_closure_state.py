#!/usr/bin/env python3
"""Fail closed unless a task PR head already contains the final closure state."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TASK_REPO_PATH = REPO_ROOT / "src" / "horadus_cli" / "task_repo.py"
TASK_REPO_SPEC = importlib.util.spec_from_file_location("horadus_task_repo_script", TASK_REPO_PATH)
if TASK_REPO_SPEC is None or TASK_REPO_SPEC.loader is None:
    raise RuntimeError(f"Unable to load task repo module from {TASK_REPO_PATH}")
task_repo_module = importlib.util.module_from_spec(TASK_REPO_SPEC)
sys.modules[TASK_REPO_SPEC.name] = task_repo_module
TASK_REPO_SPEC.loader.exec_module(task_repo_module)
TaskClosureState = task_repo_module.TaskClosureState
normalize_task_id = task_repo_module.normalize_task_id
task_closure_state = task_repo_module.task_closure_state


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

    if args.repo_root:
        override_root = Path(args.repo_root).resolve()
        task_repo_module.repo_root = lambda: override_root

    closure_state = task_closure_state(task_id)
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
