from __future__ import annotations

import subprocess  # nosec B404

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    git_bin = shared.getenv("GIT_BIN") or "git"
    return shared._run_command([git_bin, *args])
