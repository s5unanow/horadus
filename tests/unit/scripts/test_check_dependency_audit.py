from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
_SPEC = importlib.util.spec_from_file_location(
    "test_check_dependency_audit_module",
    SCRIPTS_DIR / "check_dependency_audit.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
dependency_audit_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = dependency_audit_module
_SPEC.loader.exec_module(dependency_audit_module)


def _write_report(
    *,
    path: Path,
    dependencies: list[dict[str, object]],
) -> None:
    path.write_text(json.dumps({"dependencies": dependencies, "fixes": []}), encoding="utf-8")


def test_split_findings_matches_exact_package_version_and_vulnerability() -> None:
    findings = (
        dependency_audit_module.AuditFinding(
            package="pygments",
            version="2.19.2",
            vuln_id="CVE-2026-4539",
            aliases=(),
            fix_versions=(),
            description="regex complexity",
        ),
        dependency_audit_module.AuditFinding(
            package="other-package",
            version="1.0.0",
            vuln_id="CVE-2026-9999",
            aliases=(),
            fix_versions=("1.0.1",),
            description="other issue",
        ),
    )
    allowlist = (
        dependency_audit_module.AllowlistEntry(
            vuln_id="CVE-2026-4539",
            package="pygments",
            version="2.19.2",
            reason="temporary upstream gap",
            review_after="2026-04-08",
        ),
    )

    allowed, blocked, stale = dependency_audit_module.split_findings(findings, allowlist)

    assert [finding.vuln_id for finding in allowed] == ["CVE-2026-4539"]
    assert [finding.vuln_id for finding in blocked] == ["CVE-2026-9999"]
    assert stale == ()


def test_split_findings_flags_stale_allowlist_entries() -> None:
    allowlist = (
        dependency_audit_module.AllowlistEntry(
            vuln_id="CVE-2026-4539",
            package="pygments",
            version="2.19.2",
            reason="temporary upstream gap",
            review_after="2026-04-08",
        ),
    )

    allowed, blocked, stale = dependency_audit_module.split_findings((), allowlist)

    assert allowed == ()
    assert blocked == ()
    assert stale == allowlist


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ({}, "dependency audit allowlist must contain an 'allowlist' array"),
        ({"allowlist": ["bad"]}, "dependency audit allowlist entry 0 must be an object"),
        (
            {"allowlist": [{"package": "pygments"}]},
            "dependency audit allowlist entry 0 is missing 'id'",
        ),
        (
            {
                "allowlist": [
                    {
                        "id": "CVE-2026-4539",
                        "package": "",
                        "version": "2.19.2",
                        "reason": "why",
                        "review_after": "2026-04-08",
                    }
                ]
            },
            "dependency audit allowlist entry 0 must not contain blank fields",
        ),
    ],
)
def test_load_allowlist_validation_errors(
    payload: dict[str, object], expected_message: str
) -> None:
    path = REPO_ROOT / "artifacts" / "test-dependency-audit-allowlist.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        with pytest.raises(ValueError, match=expected_message):
            dependency_audit_module.load_allowlist(path)
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ({}, "dependency audit report is missing a valid 'dependencies' array"),
        ({"dependencies": ["bad"]}, "dependency audit dependency entries must be objects"),
        (
            {"dependencies": [{"name": "", "version": "2.19.2", "vulns": []}]},
            "dependency audit dependency entries must include name and version",
        ),
        (
            {"dependencies": [{"name": "pygments", "version": "2.19.2", "vulns": {}}]},
            "dependency audit dependency 'vulns' must be a list",
        ),
        (
            {"dependencies": [{"name": "pygments", "version": "2.19.2", "vulns": ["bad"]}]},
            "dependency audit vulnerability entries must be objects",
        ),
        (
            {"dependencies": [{"name": "pygments", "version": "2.19.2", "vulns": [{"id": ""}]}]},
            "dependency audit vulnerability entries must include an id",
        ),
        (
            {
                "dependencies": [
                    {
                        "name": "pygments",
                        "version": "2.19.2",
                        "vulns": [{"id": "CVE-2026-4539", "aliases": {}, "fix_versions": []}],
                    }
                ]
            },
            "dependency audit vulnerability aliases and fix_versions must be lists",
        ),
    ],
)
def test_parse_audit_report_validation_errors(
    payload: dict[str, object], expected_message: str
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        dependency_audit_module.parse_audit_report(payload)


def test_run_command_executes_fixed_argv(tmp_path: Path) -> None:
    result = dependency_audit_module._run_command(
        ["python3", "-c", "print('dependency-audit-ok')"],
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "dependency-audit-ok"


def test_export_frozen_requirements_raises_on_failed_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependency_audit_module,
        "_run_command",
        lambda *_args, **_kwargs: dependency_audit_module.subprocess.CompletedProcess(
            ["uv"], 2, "", "export failed"
        ),
    )

    with pytest.raises(RuntimeError, match="export failed"):
        dependency_audit_module.export_frozen_requirements(
            repo_root=REPO_ROOT,
            uv_bin="uv",
            output_path=REPO_ROOT / "requirements.txt",
        )


def test_run_pip_audit_combines_stdout_and_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependency_audit_module,
        "_run_command",
        lambda *_args, **_kwargs: dependency_audit_module.subprocess.CompletedProcess(
            ["uv"], 1, "stdout line", "stderr line"
        ),
    )

    exit_code, output = dependency_audit_module.run_pip_audit(
        repo_root=REPO_ROOT,
        uv_bin="uv",
        requirements_path=REPO_ROOT / "requirements.txt",
        report_path=REPO_ROOT / "pip-audit.json",
    )

    assert exit_code == 1
    assert output == "stdout line\nstderr line"


def test_format_finding_includes_fix_versions() -> None:
    finding = dependency_audit_module.AuditFinding(
        package="pygments",
        version="2.19.2",
        vuln_id="CVE-2026-4539",
        aliases=(),
        fix_versions=("2.19.3",),
        description="regex complexity",
    )

    assert (
        dependency_audit_module._format_finding(finding)
        == "pygments 2.19.2 CVE-2026-4539 fix_versions=2.19.3"
    )


def test_main_allows_repo_owned_matching_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured_commands: list[list[str]] = []
    allowlist_path = tmp_path / "dependency_audit_allowlist.json"
    allowlist_path.write_text(
        json.dumps(
            {
                "allowlist": [
                    {
                        "id": "CVE-2026-4539",
                        "package": "pygments",
                        "version": "2.19.2",
                        "reason": "temporary upstream gap",
                        "review_after": "2026-04-08",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(
        args: list[str], *, cwd: Path
    ) -> dependency_audit_module.subprocess.CompletedProcess[str]:
        captured_commands.append(args)
        if args[1] == "export":
            output_index = args.index("-o") + 1
            Path(args[output_index]).write_text("pytest==9.0.2\n", encoding="utf-8")
            return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")
        report_index = args.index("-o") + 1
        Path(args[report_index]).write_text(
            json.dumps(
                {
                    "dependencies": [
                        {
                            "name": "pygments",
                            "version": "2.19.2",
                            "vulns": [
                                {
                                    "id": "CVE-2026-4539",
                                    "aliases": ["GHSA-5239-wwwm-4pmq"],
                                    "fix_versions": [],
                                    "description": "regex complexity",
                                }
                            ],
                        }
                    ],
                    "fixes": [],
                }
            ),
            encoding="utf-8",
        )
        return dependency_audit_module.subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(dependency_audit_module, "ALLOWLIST_PATH", allowlist_path)
    monkeypatch.setattr(dependency_audit_module, "_run_command", fake_run_command)
    monkeypatch.setattr(sys, "argv", ["check_dependency_audit.py", "uv-custom"])

    assert dependency_audit_module.main() == 0
    assert captured_commands[0][:2] == ["uv-custom", "export"]
    assert captured_commands[1][:5] == ["uv-custom", "run", "--no-sync", "python", "-m"]
    output_lines = capsys.readouterr().out.splitlines()
    assert (
        "dependency-audit: applying repo-owned allowlist entries from "
        "config/security/dependency_audit_allowlist.json"
    ) in output_lines
    assert "dependency-audit passed: no actionable vulnerabilities remain." in output_lines


def test_main_fails_for_unexpected_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allowlist_path = tmp_path / "dependency_audit_allowlist.json"
    allowlist_path.write_text(json.dumps({"allowlist": []}), encoding="utf-8")

    def fake_run_command(
        args: list[str], *, cwd: Path
    ) -> dependency_audit_module.subprocess.CompletedProcess[str]:
        if args[1] == "export":
            output_index = args.index("-o") + 1
            Path(args[output_index]).write_text("pytest==9.0.2\n", encoding="utf-8")
            return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")
        report_index = args.index("-o") + 1
        Path(args[report_index]).write_text(
            json.dumps(
                {
                    "dependencies": [
                        {
                            "name": "pygments",
                            "version": "2.19.2",
                            "vulns": [
                                {
                                    "id": "CVE-2026-4539",
                                    "aliases": [],
                                    "fix_versions": [],
                                    "description": "regex complexity",
                                }
                            ],
                        }
                    ],
                    "fixes": [],
                }
            ),
            encoding="utf-8",
        )
        return dependency_audit_module.subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(dependency_audit_module, "ALLOWLIST_PATH", allowlist_path)
    monkeypatch.setattr(dependency_audit_module, "_run_command", fake_run_command)
    monkeypatch.setattr(sys, "argv", ["check_dependency_audit.py"])

    assert dependency_audit_module.main() == 1
    output_lines = capsys.readouterr().out.splitlines()
    assert (
        "dependency-audit failed: actionable vulnerabilities remain after allowlist filtering."
        in output_lines
    )
    assert "- pygments 2.19.2 CVE-2026-4539" in output_lines


def test_main_fails_for_stale_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allowlist_path = tmp_path / "dependency_audit_allowlist.json"
    allowlist_path.write_text(
        json.dumps(
            {
                "allowlist": [
                    {
                        "id": "CVE-2026-4539",
                        "package": "pygments",
                        "version": "2.19.2",
                        "reason": "temporary upstream gap",
                        "review_after": "2026-04-08",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(
        args: list[str], *, cwd: Path
    ) -> dependency_audit_module.subprocess.CompletedProcess[str]:
        if args[1] == "export":
            output_index = args.index("-o") + 1
            Path(args[output_index]).write_text("pytest==9.0.2\n", encoding="utf-8")
            return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")
        report_index = args.index("-o") + 1
        _write_report(path=Path(args[report_index]), dependencies=[])
        return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(dependency_audit_module, "ALLOWLIST_PATH", allowlist_path)
    monkeypatch.setattr(dependency_audit_module, "_run_command", fake_run_command)
    monkeypatch.setattr(sys, "argv", ["check_dependency_audit.py"])

    assert dependency_audit_module.main() == 1
    output_lines = capsys.readouterr().out.splitlines()
    assert (
        "dependency-audit failed: stale allowlist entries no longer match current findings."
        in output_lines
    )
    assert (
        "- stale allowlist entry: pygments 2.19.2 CVE-2026-4539 (review_after=2026-04-08)"
        in output_lines
    )


def test_main_handles_non_findings_pip_audit_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allowlist_path = tmp_path / "dependency_audit_allowlist.json"
    allowlist_path.write_text(json.dumps({"allowlist": []}), encoding="utf-8")

    def fake_run_command(
        args: list[str], *, cwd: Path
    ) -> dependency_audit_module.subprocess.CompletedProcess[str]:
        if args[1] == "export":
            output_index = args.index("-o") + 1
            Path(args[output_index]).write_text("pytest==9.0.2\n", encoding="utf-8")
            return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")
        return dependency_audit_module.subprocess.CompletedProcess(
            args, 2, "audit stdout", "audit stderr"
        )

    monkeypatch.setattr(dependency_audit_module, "ALLOWLIST_PATH", allowlist_path)
    monkeypatch.setattr(dependency_audit_module, "_run_command", fake_run_command)
    monkeypatch.setattr(sys, "argv", ["check_dependency_audit.py"])

    assert dependency_audit_module.main() == 2
    output_lines = capsys.readouterr().out.splitlines()
    assert "audit stdout" in output_lines
    assert "audit stderr" in output_lines
    assert "dependency-audit: pip-audit failed before findings could be evaluated." in output_lines


def test_main_handles_non_findings_pip_audit_failure_without_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allowlist_path = tmp_path / "dependency_audit_allowlist.json"
    allowlist_path.write_text(json.dumps({"allowlist": []}), encoding="utf-8")

    def fake_run_command(
        args: list[str], *, cwd: Path
    ) -> dependency_audit_module.subprocess.CompletedProcess[str]:
        if args[1] == "export":
            output_index = args.index("-o") + 1
            Path(args[output_index]).write_text("pytest==9.0.2\n", encoding="utf-8")
            return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")
        return dependency_audit_module.subprocess.CompletedProcess(args, 2, "", "")

    monkeypatch.setattr(dependency_audit_module, "ALLOWLIST_PATH", allowlist_path)
    monkeypatch.setattr(dependency_audit_module, "_run_command", fake_run_command)
    monkeypatch.setattr(sys, "argv", ["check_dependency_audit.py"])

    assert dependency_audit_module.main() == 2
    assert capsys.readouterr().out.splitlines() == [
        "dependency-audit: auditing the exported frozen dependency set for known vulnerabilities",
        "dependency-audit: pip-audit failed before findings could be evaluated.",
    ]


def test_main_passes_without_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allowlist_path = tmp_path / "dependency_audit_allowlist.json"
    allowlist_path.write_text(json.dumps({"allowlist": []}), encoding="utf-8")

    def fake_run_command(
        args: list[str], *, cwd: Path
    ) -> dependency_audit_module.subprocess.CompletedProcess[str]:
        if args[1] == "export":
            output_index = args.index("-o") + 1
            Path(args[output_index]).write_text("pytest==9.0.2\n", encoding="utf-8")
            return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")
        report_index = args.index("-o") + 1
        _write_report(path=Path(args[report_index]), dependencies=[])
        return dependency_audit_module.subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(dependency_audit_module, "ALLOWLIST_PATH", allowlist_path)
    monkeypatch.setattr(dependency_audit_module, "_run_command", fake_run_command)
    monkeypatch.setattr(sys, "argv", ["check_dependency_audit.py"])

    assert dependency_audit_module.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "dependency-audit: auditing the exported frozen dependency set for known vulnerabilities",
        "dependency-audit passed: no actionable vulnerabilities remain.",
    ]
