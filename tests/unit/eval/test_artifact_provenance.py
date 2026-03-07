from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.eval import artifact_provenance as provenance

pytestmark = pytest.mark.unit


def test_build_source_control_provenance_handles_available_and_unavailable_git(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _next_completed(*_args, **_kwargs):
        return next(outputs)

    def _missing_git(*_args, **_kwargs):
        raise FileNotFoundError("git")

    outputs = iter(
        [
            subprocess.CompletedProcess(["git"], 0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(["git"], 0, stdout="main\n", stderr=""),
            subprocess.CompletedProcess(["git"], 0, stdout=" M file.py\n", stderr=""),
        ]
    )

    monkeypatch.setattr(provenance.subprocess, "run", _next_completed)

    available = provenance.build_source_control_provenance(repo_root=tmp_path)

    assert available["git"]["available"] is True
    assert available["git"]["commit_sha"] == "abc123"
    assert available["git"]["branch"] == "main"
    assert available["git"]["worktree_dirty"] is True

    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        _missing_git,
    )

    unavailable = provenance.build_source_control_provenance(repo_root=tmp_path)

    assert unavailable["git"]["available"] is False
    assert unavailable["git"]["commit_sha"] is None


def test_build_manifest_and_directory_provenance(tmp_path: Path) -> None:
    first = tmp_path / "one.yaml"
    second = tmp_path / "nested" / "two.yml"
    second.parent.mkdir()
    first.write_text("alpha: 1\n", encoding="utf-8")
    second.write_text("beta: 2\n", encoding="utf-8")

    manifest = provenance.build_file_manifest_provenance({"first": first, "second": second})
    directory = provenance.build_directory_provenance(directory=tmp_path)

    assert manifest["first"]["path"] == str(first)
    assert len(manifest["second"]["sha256"]) == 64
    assert directory["file_count"] == 2
    assert len(directory["fingerprint_sha256"]) == 64


def test_normalize_request_overrides_and_gold_set_fingerprints() -> None:
    assert provenance.normalize_request_overrides(None) is None
    assert provenance.normalize_request_overrides({"b": 2, "a": [3, 1]}) == {
        "a": [3, 1],
        "b": 2,
    }

    item_one = SimpleNamespace(
        item_id="2",
        title="Second",
        content="Body",
        label_verification="human_verified",
        tier1=SimpleNamespace(trend_scores={"eu-russia": 8}, max_relevance=8),
        tier2=None,
    )
    item_two = SimpleNamespace(
        item_id="1",
        title="First",
        content="Body",
        label_verification="llm_seeded",
        tier1=SimpleNamespace(trend_scores={"eu-russia": 1}, max_relevance=1),
        tier2=SimpleNamespace(
            trend_id="eu-russia",
            signal_type="military_movement",
            direction="escalatory",
            severity=0.8,
            confidence=0.9,
        ),
    )

    fingerprint = provenance.gold_set_fingerprint([item_one, item_two])
    ids_fingerprint = provenance.gold_set_item_ids_fingerprint([item_one, item_two])

    assert len(fingerprint) == 64
    assert len(ids_fingerprint) == 64
    assert fingerprint == provenance.gold_set_fingerprint([item_two, item_one])


def test_run_git_command_returns_none_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise_called_process_error(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["git"])

    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        _raise_called_process_error,
    )

    assert provenance._run_git_command(("status",), repo_root=tmp_path) is None
