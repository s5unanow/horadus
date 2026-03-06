"""Unit tests for scripts/validate_assessment_artifacts.py."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_assessment_artifacts.py"


def _run(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *[str(arg) for arg in args]],
        cwd=cwd or REPO_ROOT,
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


def test_validator_accepts_canonical_multiline_sections(tmp_path: Path) -> None:
    path = tmp_path / "2026-03-06.md"
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-example",
                "proposal_id: PROPOSAL-2026-03-06-po-example",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "Something changed.",
                "",
                "Proposed change:",
                "Do the thing.",
                "",
                "Verification:",
                "- make test-unit",
                "- python scripts/validate_assessment_artifacts.py",
                "",
                "Blast radius:",
                "- scripts/validate_assessment_artifacts.py",
                "- docs/ASSESSMENTS.md",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run(path)
    assert result.returncode == 0
    assert "passed" in result.stdout.lower()


def test_validator_rejects_empty_multiline_required_section(tmp_path: Path) -> None:
    path = tmp_path / "2026-03-06.md"
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-example",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Verification:",
                "",
                "Blast radius:",
                "- scripts/validate_assessment_artifacts.py",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run(path)
    assert result.returncode == 2
    assert "missing required fields: verification" in result.stdout


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


def test_validator_rejects_daily_title_date_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "2026-03-02.md"
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-01",
                "",
                "### PROPOSAL-2026-03-02-po-example",
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
    assert "title date mismatch" in result.stdout


def test_validator_rejects_daily_proposal_id_date_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "2026-03-02.md"
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-02",
                "",
                "### PROPOSAL-2026-03-01-po-example",
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
    assert "proposal date mismatch" in result.stdout


def test_validator_accepts_daily_date_integrity_match(tmp_path: Path) -> None:
    path = tmp_path / "2026-03-02.md"
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-02",
                "",
                "### PROPOSAL-2026-03-02-po-example",
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


def test_validator_ignores_raw_subdirectories(tmp_path: Path) -> None:
    raw_dir = tmp_path / "artifacts" / "assessments" / "agents" / "daily" / "_raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "scratch.md").write_text("not a real report\n", encoding="utf-8")

    result = _run(tmp_path / "artifacts" / "assessments")
    assert result.returncode == 0
    assert "No assessment artifacts found" in result.stdout


def test_validator_rejects_non_novel_same_role_proposal(tmp_path: Path) -> None:
    prior = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-05.md"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-05",
                "",
                "### PROPOSAL-2026-03-05-po-status-freshness-surface",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "PROJECT_STATUS is stale.",
                "",
                "Proposed change:",
                "Add a freshness surface.",
                "",
                "Verification:",
                "- make docs-freshness",
                "",
                "Blast radius:",
                "- PROJECT_STATUS.md",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-06.md"
    target.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-status-freshness-surface",
                "area: repo",
                "priority: P2",
                "confidence: 0.8",
                "estimate: 1-2h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "PROJECT_STATUS is still stale.",
                "",
                "Proposed change:",
                "Add a freshness surface.",
                "",
                "Verification:",
                "- make docs-freshness",
                "",
                "Blast radius:",
                "- PROJECT_STATUS.md",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(
        target,
        "--check-novelty",
        "--lookback-days",
        "7",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "non-novel within 7 days" in result.stdout
    assert "2026-03-05.md" in result.stdout


def test_validator_accepts_duplicate_with_explicit_delta_note(tmp_path: Path) -> None:
    prior = tmp_path / "artifacts" / "assessments" / "sa" / "daily" / "2026-03-05.md"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_text(
        "\n".join(
            [
                "# SA Daily Assessment - 2026-03-05",
                "",
                "### PROPOSAL-2026-03-05-sa-failover-policy",
                "area: processing",
                "priority: P1",
                "confidence: 0.8",
                "estimate: 2-4h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "Failover policy is unclear.",
                "",
                "Proposed change:",
                "Define degraded-mode policy.",
                "",
                "Verification:",
                "- pytest tests/unit/processing -k failover -v",
                "",
                "Blast radius:",
                "- src/processing/",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "artifacts" / "assessments" / "sa" / "daily" / "2026-03-06.md"
    target.write_text(
        "\n".join(
            [
                "# SA Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-sa-failover-policy",
                "area: processing",
                "priority: P1",
                "confidence: 0.82",
                "estimate: 2-4h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "Failover policy is still unclear.",
                "",
                "Proposed change:",
                "Define degraded-mode policy.",
                "",
                "Delta since prior report:",
                "- Added emergency-model pass criteria based on the latest canary change.",
                "",
                "Verification:",
                "- pytest tests/unit/processing -k failover -v",
                "",
                "Blast radius:",
                "- src/processing/",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(
        target,
        "--check-novelty",
        "--lookback-days",
        "7",
        cwd=tmp_path,
    )
    assert result.returncode == 0


def test_validator_rejects_proposal_already_captured_in_task_ledger(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "BACKLOG.md").write_text(
        "# Backlog\n\n### TASK-210: Launch truth single artifact\n",
        encoding="utf-8",
    )
    (tasks_dir / "COMPLETED.md").write_text("# Completed Tasks\n", encoding="utf-8")

    target = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-06.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-launch-truth-single-artifact",
                "area: repo",
                "priority: P1",
                "confidence: 0.9",
                "estimate: 2-4h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "Launch truth is fragmented.",
                "",
                "Proposed change:",
                "Create one launch truth artifact.",
                "",
                "Verification:",
                "- test -f artifacts/launch/readiness/2026-03-06.json",
                "",
                "Blast radius:",
                "- artifacts/launch/readiness/",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(
        target,
        "--check-novelty",
        "--lookback-days",
        "7",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "already captured in task ledger" in result.stdout
    assert "TASK-210" in result.stdout


def test_validator_accepts_all_clear_with_novelty_check(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "assessments" / "agents" / "daily" / "2026-03-06.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Agentic Assessment - 2026-03-06\n\nAll clear.\n", encoding="utf-8")

    result = _run(path, "--check-novelty", "--lookback-days", "7", cwd=tmp_path)
    assert result.returncode == 0
