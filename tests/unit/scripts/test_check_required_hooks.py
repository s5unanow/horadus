"""Unit tests for scripts/check_required_hooks.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_required_hooks.sh"


def _run(hooks_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), str(hooks_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_required_hooks_fails_when_hooks_missing(tmp_path: Path) -> None:
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir(parents=True)
    result = _run(hooks_dir)

    assert result.returncode == 1
    assert "Missing required executable git hook" in result.stdout


def test_check_required_hooks_passes_when_required_hooks_exist(tmp_path: Path) -> None:
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir(parents=True)
    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        hook_path = hooks_dir / hook_name
        hook_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        os.chmod(hook_path, 0o755)

    result = _run(hooks_dir)

    assert result.returncode == 0
    assert "Required git hooks installed" in result.stdout
