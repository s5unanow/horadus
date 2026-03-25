from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_secret_baseline.py"


def _load_module() -> ModuleType:
    module_name = f"check_secret_baseline_additional_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_tracked_files_requires_git_and_filters_repo_excludes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_module()
    policy = module.SecretScanPolicy(
        baseline_path=".secrets.baseline",
        exclude_pattern=r"(^docs/|^tasks/|^ai/eval/baselines/|\.env\.example$)",
    )
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="git is required"):
        module.tracked_files(tmp_path, policy)

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=b"src/app.py\0docs/readme.md\0.env.example\0scripts/task.py\0"
        ),
    )

    files = module.tracked_files(tmp_path, policy)

    assert files == ["src/app.py", "scripts/task.py"]


def test_scan_results_and_baseline_results_cover_helper_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    policy = module.SecretScanPolicy(
        baseline_path=".secrets.baseline",
        exclude_pattern=r"(^docs/|^tasks/|^ai/eval/baselines/|\.env\.example$)",
    )
    configured: list[tuple[dict[str, object], str]] = []
    scanned: list[tuple[str, ...]] = []

    class _FakeCollection:
        def scan_files(self, *files: str) -> None:
            scanned.append(files)

        def json(self) -> dict[str, list[dict[str, object]]]:
            return {"src/app.py": [{"type": "x", "hashed_secret": "y"}]}

    monkeypatch.setattr(
        module,
        "configure_settings_from_baseline",
        lambda baseline, filename: configured.append((baseline, filename)),
    )
    monkeypatch.setattr(module, "SecretsCollection", _FakeCollection)

    baseline = {"results": {"src/app.py": []}}
    assert module.scan_results(baseline=baseline, files=["src/app.py"], policy=policy) == {
        "src/app.py": [{"type": "x", "hashed_secret": "y"}]
    }
    assert configured == [(baseline, ".secrets.baseline")]
    assert scanned == [("src/app.py",)]

    assert module.baseline_results({"results": {"src/app.py": []}}) == {"src/app.py": []}
    with pytest.raises(ValueError, match="missing a valid 'results' mapping"):
        module.baseline_results({"results": []})


def test_parse_line_number_and_main_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    assert module.parse_line_number(7) == 7
    assert module.parse_line_number("8") == 8
    assert module.parse_line_number(object()) == 0

    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    config_dir = repo_root / "config" / "security"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = repo_root / ".secrets.baseline"
    baseline_path.write_text(json.dumps({"results": {}}), encoding="utf-8")
    (config_dir / "secret_scan_policy.json").write_text(
        json.dumps(
            {
                "baseline_path": ".secrets.baseline",
                "exclude_pattern": r"(^docs/|^tasks/|^ai/eval/baselines/|\.env\.example$)",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "__file__", str(scripts_dir / "check_secret_baseline.py"))

    monkeypatch.setattr(module, "tracked_files", lambda _root, _policy: [])
    assert module.main() == 0
    assert capsys.readouterr().out.splitlines() == ["secret-scan: no tracked files to scan."]

    monkeypatch.setattr(module, "tracked_files", lambda _root, _policy: ["src/app.py"])
    monkeypatch.setattr(module, "scan_results", lambda **_: {"src/app.py": []})
    monkeypatch.setattr(module, "baseline_results", lambda _baseline: {})
    monkeypatch.setattr(module, "actionable_findings", lambda **_: [])
    assert module.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "secret-scan: scanning tracked files against .secrets.baseline",
        "Secret scan passed: no actionable findings outside .secrets.baseline.",
    ]

    monkeypatch.setattr(
        module,
        "actionable_findings",
        lambda **_: [{"filename": "src/app.py", "line_number": 12, "type": "AWS Access Key"}],
    )
    assert module.main() == 1
    assert capsys.readouterr().out.splitlines() == [
        "secret-scan: scanning tracked files against .secrets.baseline",
        "Secret scan failed: findings outside .secrets.baseline were detected.",
        "- src/app.py:12 AWS Access Key",
    ]


def test_load_secret_scan_policy_rejects_missing_required_values(tmp_path: Path) -> None:
    module = _load_module()
    policy_dir = tmp_path / "config" / "security"
    policy_dir.mkdir(parents=True, exist_ok=True)

    (policy_dir / "secret_scan_policy.json").write_text(json.dumps({"baseline_path": ""}))
    with pytest.raises(ValueError, match="baseline_path"):
        module.load_secret_scan_policy(tmp_path)

    (policy_dir / "secret_scan_policy.json").write_text(
        json.dumps({"baseline_path": ".secrets.baseline"})
    )
    with pytest.raises(ValueError, match="exclude_pattern"):
        module.load_secret_scan_policy(tmp_path)
