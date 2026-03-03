"""Unit tests for scripts/check_agent_task_eligibility.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_agent_task_eligibility.sh"


def _run(task: str, *, sprint_file: Path, preflight_cmd: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TASK_ELIGIBILITY_SPRINT_FILE"] = str(sprint_file)
    env["TASK_ELIGIBILITY_PREFLIGHT_CMD"] = preflight_cmd
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), task],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_agent_task_eligibility_passes_for_active_non_human_task(tmp_path: Path) -> None:
    sprint_file = tmp_path / "CURRENT_SPRINT.md"
    sprint_file.write_text(
        "\n".join(
            [
                "## Active Tasks",
                "- `TASK-164` Add one-shot agent smoke run target",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run("TASK-164", sprint_file=sprint_file, preflight_cmd="true")
    assert result.returncode == 0
    assert "eligibility passed" in result.stdout.lower()


def test_check_agent_task_eligibility_fails_when_task_not_active(tmp_path: Path) -> None:
    sprint_file = tmp_path / "CURRENT_SPRINT.md"
    sprint_file.write_text("## Active Tasks\n- `TASK-165` Other\n", encoding="utf-8")

    result = _run("TASK-164", sprint_file=sprint_file, preflight_cmd="true")
    assert result.returncode == 1
    assert "not listed in Active Tasks" in result.stdout


def test_check_agent_task_eligibility_fails_when_task_requires_human(tmp_path: Path) -> None:
    sprint_file = tmp_path / "CURRENT_SPRINT.md"
    sprint_file.write_text(
        "## Active Tasks\n- `TASK-080` Telegram wiring [REQUIRES_HUMAN]\n",
        encoding="utf-8",
    )

    result = _run("TASK-080", sprint_file=sprint_file, preflight_cmd="true")
    assert result.returncode == 1
    assert "[REQUIRES_HUMAN]" in result.stdout


def test_check_agent_task_eligibility_fails_when_preflight_fails(tmp_path: Path) -> None:
    sprint_file = tmp_path / "CURRENT_SPRINT.md"
    sprint_file.write_text(
        "## Active Tasks\n- `TASK-164` Add one-shot agent smoke run target\n",
        encoding="utf-8",
    )

    result = _run("TASK-164", sprint_file=sprint_file, preflight_cmd="false")
    assert result.returncode == 1
    assert "preflight failed" in result.stdout.lower()
