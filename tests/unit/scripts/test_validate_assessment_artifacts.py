"""Unit tests for scripts/validate_assessment_artifacts.py."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_assessment_artifacts.py"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _run(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *[str(arg) for arg in args]],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _import_internal(module_name: str):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return importlib.import_module(f"validate_assessment_artifacts_lib.{module_name}")


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


def test_validator_novelty_ignores_future_artifacts(tmp_path: Path) -> None:
    future = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-07.md"
    future.parent.mkdir(parents=True, exist_ok=True)
    future.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-07",
                "",
                "### PROPOSAL-2026-03-07-po-status-freshness-surface",
                "area: repo",
                "priority: P2",
                "confidence: 0.8",
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

    result = _run(
        target,
        "--check-novelty",
        "--lookback-days",
        "7",
        cwd=tmp_path,
    )
    assert result.returncode == 0


def _write_current_sprint(tmp_path: Path, *, active_tasks: list[str]) -> None:
    active_lines = "\n".join(f"- `{task_id}` Active test task" for task_id in active_tasks)
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks" / "CURRENT_SPRINT.md").write_text(
        "\n".join(
            [
                "# Current Sprint",
                "",
                "**Sprint Goal**: Test grounding",
                "**Sprint Number**: 3",
                "**Sprint Dates**: 2026-03-04 to 2026-03-18",
                "",
                "## Active Tasks",
                "",
                active_lines,
                "",
                "## Completed This Sprint",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_validator_accepts_current_sprint_task_reference(tmp_path: Path) -> None:
    _write_current_sprint(tmp_path, active_tasks=["TASK-189"])
    path = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-06.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-health-guard",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "`TASK-189` remains an active blocker in the current sprint.",
                "",
                "Proposed change:",
                "Keep the blocker visible in the launch view.",
                "",
                "Verification:",
                '- rg -n "TASK-189" tasks/CURRENT_SPRINT.md',
                "",
                "Blast radius:",
                "- tasks/CURRENT_SPRINT.md",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(path, "--check-sprint-grounding", cwd=tmp_path)
    assert result.returncode == 0


def test_validator_rejects_stale_current_sprint_task_reference(tmp_path: Path) -> None:
    _write_current_sprint(tmp_path, active_tasks=["TASK-189"])
    path = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-06.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-stale-blocker-reference",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "`TASK-193` remains an active blocker in the current sprint.",
                "",
                "Proposed change:",
                "Remove stale blocker references before publish.",
                "",
                "Verification:",
                '- rg -n "TASK-193" artifacts/assessments/po/daily/2026-03-06.md',
                "",
                "Blast radius:",
                "- artifacts/assessments/po/daily/",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(path, "--check-sprint-grounding", cwd=tmp_path)
    assert result.returncode == 2
    assert "TASK-193" in result.stdout
    assert "tasks/CURRENT_SPRINT.md Active Tasks" in result.stdout


def test_validator_accepts_historical_task_reference_marker(tmp_path: Path) -> None:
    _write_current_sprint(tmp_path, active_tasks=["TASK-189"])
    path = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-06.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-historical-reference",
                "area: docs",
                "priority: P3",
                "confidence: 0.6",
                "estimate: <1h",
                "recommended_gate: AUTO_OK",
                "",
                "Problem:",
                "[historical] TASK-193 was previously referenced as an active blocker.",
                "",
                "Proposed change:",
                "Document the marker convention for non-current task references.",
                "",
                "Verification:",
                "- python scripts/validate_assessment_artifacts.py 2026-03-06.md --check-sprint-grounding",
                "",
                "Blast radius:",
                "- docs/ASSESSMENTS.md",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(path, "--check-sprint-grounding", cwd=tmp_path)
    assert result.returncode == 0


def test_validator_accepts_cross_role_unique_proposal(tmp_path: Path) -> None:
    prior = tmp_path / "artifacts" / "assessments" / "security" / "daily" / "2026-03-05.md"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_text(
        "\n".join(
            [
                "# Security Assessment - 2026-03-05",
                "",
                "### FINDING-2026-03-05-security-public-metrics-surface",
                "area: security",
                "priority: P1",
                "confidence: 0.9",
                "estimate: 1-2h",
                "recommended_gate: REQUIRES_HUMAN",
                "",
                "Problem:",
                "Metrics are public.",
                "",
                "Proposed change:",
                "Require auth for metrics endpoints.",
                "",
                "Verification:",
                "- curl -i /metrics",
                "",
                "Blast radius:",
                "- src/api/routes/metrics.py",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "artifacts" / "assessments" / "sa" / "daily" / "2026-03-06.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "# SA Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-sa-failover-quality-sentinel",
                "area: processing",
                "priority: P1",
                "confidence: 0.8",
                "estimate: 2-4h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "Failover lacks a quality sentinel.",
                "",
                "Proposed change:",
                "Track failover quality with sampled comparisons.",
                "",
                "Verification:",
                "- pytest tests/unit/processing -k failover -v",
                "",
                "Blast radius:",
                "- src/processing/llm_failover.py",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(
        target,
        "--check-cross-role-overlap",
        "--lookback-days",
        "7",
        cwd=tmp_path,
    )
    assert result.returncode == 0


def test_validator_rejects_cross_role_overlap(tmp_path: Path) -> None:
    prior = tmp_path / "artifacts" / "assessments" / "security" / "daily" / "2026-03-05.md"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_text(
        "\n".join(
            [
                "# Security Assessment - 2026-03-05",
                "",
                "### FINDING-2026-03-05-security-observability-endpoints-public",
                "area: security",
                "priority: P1",
                "confidence: 0.95",
                "estimate: 1-2h",
                "recommended_gate: REQUIRES_HUMAN",
                "",
                "Problem:",
                "Health and metrics endpoints are publicly reachable without auth.",
                "",
                "Proposed change:",
                "Require auth or allowlisting for all privileged diagnostics.",
                "",
                "Verification:",
                "- curl -i /health /health/ready /metrics",
                "",
                "Blast radius:",
                "- src/api/routes/health.py",
                "- src/api/routes/metrics.py",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "artifacts" / "assessments" / "sa" / "daily" / "2026-03-06.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "# SA Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-sa-observability-endpoints-public",
                "area: security",
                "priority: P1",
                "confidence: 0.82",
                "estimate: 1d",
                "recommended_gate: REQUIRES_HUMAN",
                "",
                "Problem:",
                "Health and metrics endpoints are publicly reachable without auth.",
                "",
                "Proposed change:",
                "Require auth or allowlisting for all privileged diagnostics.",
                "",
                "Verification:",
                "- curl -i /health /health/ready /metrics",
                "",
                "Blast radius:",
                "- src/api/routes/health.py",
                "- src/api/routes/metrics.py",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(
        target,
        "--check-cross-role-overlap",
        "--lookback-days",
        "7",
        cwd=tmp_path,
    )
    expected_overlap_id = (
        "FINDING-2026-03-05-security-observability-endpoints-public"  # pragma: allowlist secret
    )
    assert result.returncode == 2
    assert "overlaps with recent security proposal" in result.stdout
    assert expected_overlap_id in result.stdout


def test_validator_accepts_cross_role_overlap_with_explicit_delta(tmp_path: Path) -> None:
    prior = tmp_path / "artifacts" / "assessments" / "security" / "daily" / "2026-03-05.md"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_text(
        "\n".join(
            [
                "# Security Assessment - 2026-03-05",
                "",
                "### FINDING-2026-03-05-security-observability-endpoints-public",
                "area: security",
                "priority: P1",
                "confidence: 0.95",
                "estimate: 1-2h",
                "recommended_gate: REQUIRES_HUMAN",
                "",
                "Problem:",
                "Health and metrics endpoints are publicly reachable without auth.",
                "",
                "Proposed change:",
                "Require auth or allowlisting for all privileged diagnostics.",
                "",
                "Verification:",
                "- curl -i /health /health/ready /metrics",
                "",
                "Blast radius:",
                "- src/api/routes/health.py",
                "- src/api/routes/metrics.py",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "artifacts" / "assessments" / "sa" / "daily" / "2026-03-06.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "# SA Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-sa-observability-endpoints-public",
                "area: security",
                "priority: P1",
                "confidence: 0.84",
                "estimate: 1d",
                "recommended_gate: REQUIRES_HUMAN",
                "",
                "Problem:",
                "Health and metrics endpoints are publicly reachable without auth.",
                "",
                "Proposed change:",
                "Require auth or allowlisting for all privileged diagnostics.",
                "",
                "New evidence:",
                "- Architecture review adds ingress-policy drift controls missing from the security finding.",
                "",
                "Verification:",
                "- curl -i /health /health/ready /metrics",
                "",
                "Blast radius:",
                "- src/api/routes/health.py",
                "- src/api/routes/metrics.py",
                "- docs/DEPLOYMENT.md",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run(
        target,
        "--check-cross-role-overlap",
        "--lookback-days",
        "7",
        cwd=tmp_path,
    )
    assert result.returncode == 0


def test_internal_grounding_pass_is_independently_invocable(tmp_path: Path) -> None:
    grounding = _import_internal("grounding")
    _write_current_sprint(tmp_path, active_tasks=["TASK-189"])

    path = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-06.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-06",
                "",
                "### PROPOSAL-2026-03-06-po-stale-blocker-reference",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "recommended_gate: HUMAN_REVIEW",
                "",
                "Problem:",
                "`TASK-193` remains an active blocker in the current sprint.",
                "",
                "Proposed change:",
                "Remove stale blocker references before publish.",
                "",
                "Verification:",
                '- rg -n "TASK-193" artifacts/assessments/po/daily/2026-03-06.md',
                "",
                "Blast radius:",
                "- artifacts/assessments/po/daily/",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    findings = grounding.grounding_findings_for_file(path, repo_root=tmp_path)
    assert len(findings) == 1
    assert findings[0].line_no == 11
    assert "TASK-193" in findings[0].message


def test_internal_novelty_pass_is_independently_invocable(tmp_path: Path) -> None:
    novelty = _import_internal("novelty")

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

    findings = novelty.novelty_findings_for_file(
        target,
        lookback_days=7,
        all_files=[prior, target],
        repo_root=tmp_path,
    )
    assert len(findings) == 2
    assert "non-novel within 7 days" in findings[0].message
    assert "no materially new proposals remain" in findings[1].message
