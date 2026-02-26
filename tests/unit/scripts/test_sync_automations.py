from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync_automations.py"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_export_drops_timestamps(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    repo_dir = tmp_path / "repo"

    (repo_dir / "ids.txt").parent.mkdir(parents=True, exist_ok=True)
    (repo_dir / "ids.txt").write_text("weekly-backlog-triage\n", encoding="utf-8")

    src = codex_home / "automations" / "weekly-backlog-triage" / "automation.toml"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        "\n".join(
            [
                "version = 1",
                'id = "weekly-backlog-triage"',
                'name = "Weekly backlog triage"',
                'prompt = "hello\\nworld"',
                'status = "ACTIVE"',
                'rrule = "FREQ=WEEKLY;BYDAY=SU;BYHOUR=18;BYMINUTE=0"',
                'cwds = ["/tmp"]',
                "created_at = 1",
                "updated_at = 2",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run(
        "export",
        "--codex-home",
        str(codex_home),
        "--repo-dir",
        str(repo_dir),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    spec = (repo_dir / "specs" / "weekly-backlog-triage.toml").read_text(encoding="utf-8")
    assert "created_at" not in spec
    assert "updated_at" not in spec
    assert 'id = "weekly-backlog-triage"' in spec


def test_apply_preserves_created_at_and_updates_fields(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    repo_dir = tmp_path / "repo"

    (repo_dir / "ids.txt").write_text("daily-sprint-health\n", encoding="utf-8")
    (repo_dir / "specs").mkdir(parents=True, exist_ok=True)
    (repo_dir / "specs" / "daily-sprint-health.toml").write_text(
        "\n".join(
            [
                "version = 1",
                'id = "daily-sprint-health"',
                'name = "Daily sprint health"',
                'prompt = "p"',
                'status = "PAUSED"',
                'rrule = "FREQ=WEEKLY;BYHOUR=5;BYMINUTE=0;BYDAY=SU"',
                'execution_environment = "local"',
                'cwds = ["/Users/example/repo"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    dest = codex_home / "automations" / "daily-sprint-health" / "automation.toml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "\n".join(
            [
                "version = 1",
                'id = "daily-sprint-health"',
                'name = "Daily sprint health"',
                'prompt = "old"',
                'status = "ACTIVE"',
                'rrule = "FREQ=WEEKLY;BYHOUR=5;BYMINUTE=0;BYDAY=SU"',
                'execution_environment = "local"',
                'cwds = ["/Users/example/repo"]',
                "created_at = 123",
                "updated_at = 456",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run(
        "apply",
        "--codex-home",
        str(codex_home),
        "--repo-dir",
        str(repo_dir),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    new_toml = dest.read_text(encoding="utf-8")
    assert "created_at = 123" in new_toml
    assert 'status = "PAUSED"' in new_toml
    assert 'prompt = "p"' in new_toml
    assert "updated_at = 456" not in new_toml
