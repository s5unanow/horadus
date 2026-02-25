"""Unit tests for scripts/validate_assessment_artifacts.py."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_assessment_artifacts.py"


def _run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *[str(p) for p in paths]],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_validator_accepts_all_clear(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# Report\n\nAll clear.\n", encoding="utf-8")
    result = _run(path)
    assert result.returncode == 0


def test_validator_accepts_valid_proposal(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text(
        "\n".join(
            [
                "# Report",
                "",
                "### PROPOSAL-2026-02-25-po-example",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "verification: make test-unit",
                "blast_radius: scripts/",
                "recommended_gate: HUMAN_REVIEW",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run(path)
    assert result.returncode == 0
    assert "passed" in result.stdout.lower()


def test_validator_rejects_task_heading(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text(
        "\n".join(
            [
                "# Report",
                "",
                "### TASK-123: Bad",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "verification: make test-unit",
                "blast_radius: scripts/",
                "recommended_gate: HUMAN_REVIEW",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run(path)
    assert result.returncode == 2
    assert "forbidden heading" in result.stdout


def test_validator_rejects_invalid_confidence(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text(
        "\n".join(
            [
                "# Report",
                "",
                "### PROPOSAL-2026-02-25-po-bad",
                "area: repo",
                "priority: P2",
                "confidence: 2.0",
                "estimate: 1-2h",
                "verification: make test-unit",
                "blast_radius: scripts/",
                "recommended_gate: HUMAN_REVIEW",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run(path)
    assert result.returncode == 2
    assert "invalid confidence" in result.stdout
