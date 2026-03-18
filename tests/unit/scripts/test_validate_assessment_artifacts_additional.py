from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _import_internal(module_name: str):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return importlib.import_module(f"validate_assessment_artifacts_lib.{module_name}")


def test_artifacts_helpers_cover_inline_sections_and_invalid_inputs(tmp_path: Path) -> None:
    artifacts = _import_internal("artifacts")
    models = _import_internal("models")

    raw_dir = tmp_path / "artifacts" / "_raw"
    raw_dir.mkdir(parents=True)
    kept = tmp_path / "artifacts" / "kept.md"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text("# kept\n", encoding="utf-8")
    (raw_dir / "ignored.md").write_text("# ignored\n", encoding="utf-8")

    files = artifacts.iter_markdown_files([tmp_path / "artifacts", kept])
    assert files == [kept, kept]
    assert artifacts.parse_confidence("oops") is None
    assert artifacts.artifact_file_date(Path("notes.md")) is None
    assert artifacts.normalize_non_field_section("Unexpected Heading") is None

    fields, sections = artifacts.parse_block_content(
        [
            "Verification:",
            "- make test-unit",
            "Custom heading:",
            "",
            "Problem: Something drifted",
            "Proposed change:",
            "Tighten the gate.",
            "",
        ],
        start_line_no=10,
    )
    assert fields == {"verification": "- make test-unit\nCustom heading:"}
    assert sections == {
        "problem": "Something drifted",
        "proposed_change": "Tighten the gate.",
    }

    proposal = models.ProposalBlock(
        proposal_id="PROPOSAL-2026-03-18-po-example",
        line_no=3,
        fields={"verification": "- make test-unit", "blast_radius": "- scripts/"},
        sections={"problem": "A", "proposed_change": "B"},
    )
    assert artifacts.proposal_body_text(proposal) == "A\nB\n- make test-unit\n- scripts/"


def test_grounding_history_novelty_overlap_and_runner_helper_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grounding = _import_internal("grounding")
    history = _import_internal("history")
    novelty = _import_internal("novelty")
    overlap = _import_internal("overlap")
    runner = _import_internal("runner")
    models = _import_internal("models")

    backlog = tmp_path / "tasks" / "BACKLOG.md"
    completed = tmp_path / "tasks" / "COMPLETED.md"
    backlog.parent.mkdir(parents=True, exist_ok=True)
    backlog.write_text(
        "### TASK-351: Tighten scripts gate posture\n",
        encoding="utf-8",
    )
    completed.write_text(
        "## Sprint 9\n- TASK-352: Close sprint ledger ✅\n",
        encoding="utf-8",
    )
    assert history.load_task_titles(tmp_path) == [
        ("TASK-351", "Tighten scripts gate posture"),
        ("TASK-352", "Close sprint ledger"),
    ]

    empty_repo = tmp_path / "empty"
    empty_repo.mkdir()
    assert history.load_current_sprint_truth(empty_repo) == ({}, None)
    sprint_file = tmp_path / "tasks" / "CURRENT_SPRINT.md"
    sprint_file.write_text("# Current Sprint\n\n**Sprint Number**: 9\n", encoding="utf-8")
    assert history.load_current_sprint_truth(tmp_path) == ({}, None)

    report = tmp_path / "artifacts" / "assessments" / "po" / "daily" / "2026-03-18.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("TASK-999 is current.\n", encoding="utf-8")
    monkeypatch.setattr(
        grounding, "load_current_sprint_truth", lambda _root: ({"TASK-351": 8}, None)
    )
    monkeypatch.setattr(grounding, "artifact_file_date", lambda _path: None)
    assert grounding.grounding_findings_for_file(report, repo_root=tmp_path) == []

    monkeypatch.setattr(
        grounding,
        "load_current_sprint_truth",
        lambda _root: ({"TASK-351": 8}, (date(2026, 3, 1), date(2026, 3, 7))),
    )
    monkeypatch.setattr(grounding, "artifact_file_date", lambda _path: date(2026, 3, 18))
    assert grounding.grounding_findings_for_file(report, repo_root=tmp_path) == []

    target = tmp_path / "target.md"
    no_role = tmp_path / "no-role.md"
    other_role = tmp_path / "other-role.md"
    old_role = tmp_path / "old-role.md"
    future_role = tmp_path / "future-role.md"
    good_role = tmp_path / "good-role.md"
    dates = {
        target: date(2026, 3, 18),
        no_role: date(2026, 3, 17),
        other_role: date(2026, 3, 17),
        old_role: date(2026, 2, 20),
        future_role: date(2026, 3, 19),
        good_role: date(2026, 3, 15),
    }
    roles = {
        no_role: None,
        other_role: "security",
        old_role: "po",
        future_role: "po",
        good_role: "po",
    }
    monkeypatch.setattr(history, "artifact_file_date", lambda path: dates[path])
    monkeypatch.setattr(
        history,
        "iter_markdown_files",
        lambda _paths: [target, no_role, other_role, old_role, future_role, good_role],
    )
    monkeypatch.setattr(
        history,
        "parse_artifact",
        lambda path: SimpleNamespace(path=path, role=roles[path], proposals=()),
    )
    history_matches = history.history_artifacts_for_file(
        SimpleNamespace(path=target, role="po"),
        lookback_days=7,
        all_files=[target, no_role, other_role, old_role, future_role, good_role],
        repo_root=tmp_path,
        include_same_role=True,
    )
    assert [artifact.path for artifact in history_matches] == [good_role]
    other_role_matches = history.history_artifacts_for_file(
        SimpleNamespace(path=target, role="po"),
        lookback_days=7,
        all_files=[target, other_role, good_role],
        repo_root=empty_repo,
        include_same_role=False,
    )
    assert [artifact.path for artifact in other_role_matches] == [other_role]

    first = models.ProposalBlock(
        proposal_id="PROPOSAL-2026-03-10-po-docs-note",
        line_no=3,
        fields={"verification": "- make agent-check", "blast_radius": "- scripts/"},
        sections={"problem": "unrelated drift", "proposed_change": "touch docs only"},
    )
    second = models.ProposalBlock(
        proposal_id="PROPOSAL-2026-03-12-po-scripts-gate-posture",
        line_no=3,
        fields={"verification": "- make agent-check", "blast_radius": "- scripts/"},
        sections={
            "problem": "scripts gate posture drifted in CI",
            "proposed_change": "cover scripts and entrypoints",
        },
    )
    chosen = novelty.similar_history_match(
        second,
        history=[
            models.ParsedArtifact(
                path=tmp_path / "older.md", role="po", is_all_clear=False, proposals=(first,)
            ),
            models.ParsedArtifact(
                path=tmp_path / "newer.md", role="po", is_all_clear=False, proposals=(second,)
            ),
        ],
    )
    assert chosen is not None
    assert chosen[1].name == "newer.md"
    assert novelty.token_similarity(set(), {"scripts"}) == 0.0
    assert novelty.normalize_slug("custom-topic") == "custom-topic"
    retained = novelty.similar_history_match(
        second,
        history=[
            models.ParsedArtifact(
                path=tmp_path / "best.md", role="po", is_all_clear=False, proposals=(second,)
            ),
            models.ParsedArtifact(
                path=tmp_path / "worse.md",
                role="po",
                is_all_clear=False,
                proposals=(
                    models.ProposalBlock(
                        proposal_id="PROPOSAL-2026-03-11-po-scripts-gate",
                        line_no=3,
                        fields={
                            "verification": "- make agent-check",
                            "blast_radius": "- scripts/",
                        },
                        sections={
                            "problem": "scripts changed",
                            "proposed_change": "cover gate",
                        },
                    ),
                ),
            ),
        ],
    )
    assert retained is not None
    assert retained[1].name == "best.md"

    task_report = tmp_path / "artifact.md"
    task_report.write_text("# report\n", encoding="utf-8")
    task_proposal = models.ProposalBlock(
        proposal_id="PROPOSAL-2026-03-18-po-scripts-gate-posture",
        line_no=3,
        fields={"verification": "- make agent-check", "blast_radius": "- scripts/"},
        sections={"problem": "scripts gate posture drift", "proposed_change": "cover scripts"},
    )
    monkeypatch.setattr(
        novelty,
        "parse_artifact",
        lambda _path: models.ParsedArtifact(
            path=task_report,
            role="po",
            is_all_clear=False,
            proposals=(task_proposal,),
        ),
    )
    monkeypatch.setattr(novelty, "history_artifacts_for_file", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        novelty,
        "load_task_titles",
        lambda _root: [
            ("TASK-100", "minor unrelated task"),
            ("TASK-351", "tighten scripts gate posture"),
        ],
    )
    novelty_findings = novelty.novelty_findings_for_file(
        task_report,
        lookback_days=7,
        all_files=[task_report],
        repo_root=tmp_path,
    )
    assert len(novelty_findings) == 2
    assert "already captured in task ledger by TASK-351" in novelty_findings[0].message
    assert "no materially new proposals remain" in novelty_findings[1].message

    overlap_report = tmp_path / "overlap.md"
    overlap_report.write_text("# report\n", encoding="utf-8")
    monkeypatch.setattr(
        overlap,
        "parse_artifact",
        lambda _path: models.ParsedArtifact(
            path=overlap_report,
            role="po",
            is_all_clear=False,
            proposals=(task_proposal,),
        ),
    )
    monkeypatch.setattr(overlap, "history_artifacts_for_file", lambda *_args, **_kwargs: [])
    assert (
        overlap.cross_role_overlap_findings_for_file(
            overlap_report,
            lookback_days=7,
            all_files=[overlap_report],
            repo_root=tmp_path,
        )
        == []
    )
    monkeypatch.setattr(
        overlap,
        "parse_artifact",
        lambda _path: models.ParsedArtifact(
            path=overlap_report,
            role=None,
            is_all_clear=False,
            proposals=(task_proposal,),
        ),
    )
    assert (
        overlap.cross_role_overlap_findings_for_file(
            overlap_report,
            lookback_days=7,
            all_files=[overlap_report],
            repo_root=tmp_path,
        )
        == []
    )

    with pytest.raises(SystemExit, match="2"):
        runner.main(["--lookback-days", "-1"])


def test_schema_validation_additional_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = _import_internal("schema_validation")
    models = _import_internal("models")

    missing_title = tmp_path / "2026-03-18.md"
    missing_title.write_text("# PO Daily Assessment\n", encoding="utf-8")
    findings = schema.validate_file(missing_title)
    messages = [finding.message for finding in findings]
    assert any("daily report title missing date" in message for message in messages)
    assert any("no proposals found" in message for message in messages)

    missing_proposal_date = tmp_path / "2026-03-19.md"
    missing_proposal_date.write_text(
        "\n".join(
            [
                "# PO Daily Assessment - 2026-03-19",
                "",
                "### PROPOSAL-po-scripts-gate-posture",
                "area: repo",
                "priority: P2",
                "confidence: 0.7",
                "estimate: 1-2h",
                "verification: make agent-check",
                "blast_radius: scripts/",
                "recommended_gate: HUMAN_REVIEW",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    findings = schema.validate_file(missing_proposal_date)
    assert any(
        "missing YYYY-MM-DD segment matching filename date 2026-03-19" in f.message
        for f in findings
    )

    synthetic = tmp_path / "synthetic.md"
    synthetic.write_text("# Synthetic\n", encoding="utf-8")
    proposal = models.ProposalBlock(
        proposal_id="PROPOSAL-2026-03-20-po-scripts-gate-posture",
        line_no=3,
        fields={},
        sections={},
    )
    monkeypatch.setattr(
        schema,
        "parse_artifact",
        lambda _path: models.ParsedArtifact(
            path=synthetic,
            role="po",
            is_all_clear=False,
            proposals=(proposal,),
        ),
    )
    monkeypatch.setattr(
        schema,
        "parse_block_content",
        lambda _block_lines, _start_line_no: (
            {
                "area": "mystery",
                "priority": "P9",
                "confidence": "unknown",
                "estimate": " ",
                "verification": " ",
                "blast_radius": " ",
                "recommended_gate": "AUTO_MERGE",
            },
            {},
        ),
    )
    findings = schema.validate_file(synthetic)
    messages = [finding.message for finding in findings]
    assert any("invalid area 'mystery'" in message for message in messages)
    assert any("invalid priority 'P9'" in message for message in messages)
    assert any("invalid confidence 'unknown'" in message for message in messages)
    assert any("invalid recommended_gate 'AUTO_MERGE'" in message for message in messages)
    assert any("'estimate' must be non-empty" in message for message in messages)
    assert any("'verification' must be non-empty" in message for message in messages)
    assert any("'blast_radius' must be non-empty" in message for message in messages)
