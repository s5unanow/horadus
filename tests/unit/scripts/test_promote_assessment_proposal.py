"""Unit tests for scripts/promote_assessment_proposal.sh."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "promote_assessment_proposal.sh"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_assessment(path: Path, *, title_date: str, proposal_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# Role Daily Assessment - {title_date}",
                "",
                f"### {proposal_id}",
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


def test_promote_assessment_proposal_unique_pass(tmp_path: Path) -> None:
    result = _run(
        "--proposal-id",
        "PROPOSAL-2026-03-02-po-unique-topic",
        "--assessment-ref",
        "artifacts/assessments/po/daily/2026-03-02.md",
        "--title",
        "Unique topic",
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert "Potential duplicate" not in result.stdout
    assert "### TASK-XXX: Unique topic" in result.stdout


def test_promote_assessment_proposal_duplicate_warn(tmp_path: Path) -> None:
    _seed_assessment(
        tmp_path / "artifacts/assessments/sa/daily/2026-03-01.md",
        title_date="2026-03-01",
        proposal_id="PROPOSAL-2026-03-01-sa-cross-stage-slo-budget",
    )

    result = _run(
        "--proposal-id",
        "PROPOSAL-2026-03-02-po-cross-stage-slo-budget",
        "--assessment-ref",
        "artifacts/assessments/po/daily/2026-03-02.md",
        "--title",
        "Cross-stage SLO budget",
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert "Potential duplicate proposals detected" in result.stdout
    assert "matched prior (proposal_id, Assessment-Ref)" in result.stdout
    assert "### TASK-XXX: Cross-stage SLO budget" in result.stdout


def test_promote_assessment_proposal_duplicate_strict_fail(tmp_path: Path) -> None:
    _seed_assessment(
        tmp_path / "artifacts/assessments/agents/daily/2026-03-01.md",
        title_date="2026-03-01",
        proposal_id="PROPOSAL-2026-03-01-agents-task-eligibility-preflight",
    )

    result = _run(
        "--proposal-id",
        "PROPOSAL-2026-03-02-po-task-eligibility-preflight",
        "--assessment-ref",
        "artifacts/assessments/po/daily/2026-03-02.md",
        "--title",
        "Task eligibility preflight",
        "--strict-dedupe",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "Strict mode enabled" in result.stdout
