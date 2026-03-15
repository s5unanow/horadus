from __future__ import annotations

import subprocess  # nosec B404

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    git_bin = shared.getenv("GIT_BIN") or "git"
    command = [git_bin, *args]
    try:
        return shared._run_command(command)
    except OSError as exc:
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr=str(exc),
        )
