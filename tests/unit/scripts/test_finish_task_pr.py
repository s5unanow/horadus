"""Unit tests for the finish-task compatibility wrapper."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "finish_task_pr.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_finish_task_pr_delegates_to_horadus_cli(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    captured_args = tmp_path / "uv-args.txt"

    _write_executable(
        bin_dir / "uv",
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "{captured_args}"
echo "wrapper-ok"
""",
    )

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "TASK-258"],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "wrapper-ok"
    assert captured_args.read_text(encoding="utf-8").splitlines() == [
        "run",
        "--no-sync",
        "horadus",
        "tasks",
        "finish",
        "TASK-258",
    ]
