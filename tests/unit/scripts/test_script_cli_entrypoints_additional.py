from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _run_script(
    script_name: str,
    tmp_path: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPTS_DIR / script_name), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_script_without_repo_root(stem: str) -> ModuleType:
    module_name = f"script_entrypoint_{stem}_{len(sys.modules)}"
    original_path = list(sys.path)
    sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != REPO_ROOT]
    try:
        spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / f"{stem}.py")
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original_path


@pytest.mark.parametrize(
    ("script_name", "args", "expected_output"),
    [
        ("check_code_shape.py", ("--help",), "usage:"),
        ("check_docs_freshness.py", ("--help",), "usage:"),
        ("check_pr_review_gate.py", ("--help",), "usage:"),
        (
            "check_secret_baseline.py",
            (),
            "Secret scan passed: no actionable findings outside .secrets.baseline.",
        ),
        ("release_gate_runtime.py", ("--help",), "usage:"),
        ("seed_trends.py", ("--help",), "usage:"),
        ("sync_automations.py", ("--help",), "usage:"),
    ],
)
def test_script_help_entrypoints_execute_from_external_cwd(
    script_name: str,
    args: tuple[str, ...],
    expected_output: str,
    tmp_path: Path,
) -> None:
    result = _run_script(script_name, tmp_path, *args)

    assert result.returncode == 0
    assert expected_output.lower() in result.stdout.lower()


@pytest.mark.parametrize(
    ("stem", "attribute"),
    [
        ("check_dependency_audit", "main"),
        ("check_code_shape", "main"),
        ("check_docs_freshness", "main"),
        ("check_pr_closure_state", "main"),
        ("check_pr_review_gate", "main"),
    ],
)
def test_script_imports_insert_repo_root_when_missing(stem: str, attribute: str) -> None:
    module = _load_script_without_repo_root(stem)
    assert hasattr(module, attribute)


def test_check_dependency_audit_script_entrypoint_executes_main(tmp_path: Path) -> None:
    fake_uv = tmp_path / "fake-uv"
    fake_uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "export" ]]; then
  output=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then
      output="$2"
      shift 2
      continue
    fi
    shift
  done
  printf 'pytest==9.0.2\\n' >"$output"
  exit 0
fi
output=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-o" ]]; then
    output="$2"
    shift 2
    continue
  fi
  shift
done
cat >"$output" <<'JSON'
{"dependencies":[{"name":"pygments","version":"2.19.2","vulns":[{"id":"CVE-2026-4539","aliases":[],"fix_versions":[],"description":"regex complexity"}]}],"fixes":[]}
JSON
exit 1
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    result = _run_script("check_dependency_audit.py", tmp_path, str(fake_uv))

    assert result.returncode == 0
    assert "dependency-audit passed: no actionable vulnerabilities remain." in result.stdout
