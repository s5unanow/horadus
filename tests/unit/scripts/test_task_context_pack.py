"""Unit tests for scripts/task_context_pack.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "task_context_pack.sh"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _fake_uv_env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_path = bin_dir / "uv"
    uv_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" != "run" || "$2" != "--no-sync" || "$3" != "horadus" || "$4" != "tasks" || "$5" != "context-pack" ]]; then
  echo "unexpected invocation: $*" >&2
  exit 99
fi

task_id="$6"
include_archive="${7:-}"

if [[ "$task_id" == "TASK-301" ]]; then
  printf '# Context Pack: TASK-301\n## Suggested Validation Commands\nmake agent-check\n'
  exit 0
fi

if [[ "$task_id" == "TASK-302" && "$include_archive" == "--include-archive" ]]; then
  printf '# Context Pack: TASK-302\n'
  exit 0
fi

if [[ "$task_id" == "invalid" ]]; then
  printf 'Invalid task id\n'
  exit 1
fi

echo "unexpected task invocation: $*" >&2
exit 98
""",
        encoding="utf-8",
    )
    uv_path.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HORADUS_CLI_WRAPPER_SILENT": "1",
    }


def test_task_context_pack_prints_task_context(tmp_path: Path) -> None:
    result = _run("TASK-301", env=_fake_uv_env(tmp_path))
    assert result.returncode == 0
    assert "# Context Pack: TASK-301" in result.stdout
    assert "## Suggested Validation Commands" in result.stdout
    assert "make agent-check" in result.stdout


def test_task_context_pack_supports_explicit_archive_lookup(tmp_path: Path) -> None:
    result = _run("TASK-302", "--include-archive", env=_fake_uv_env(tmp_path))
    assert result.returncode == 0
    assert "# Context Pack: TASK-302" in result.stdout


def test_task_context_pack_rejects_invalid_task_id(tmp_path: Path) -> None:
    result = _run("invalid", env=_fake_uv_env(tmp_path))
    assert result.returncode == 1
    assert "Invalid task id" in result.stdout
