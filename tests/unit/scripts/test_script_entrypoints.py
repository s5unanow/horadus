from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_script_module(stem: str) -> ModuleType:
    path = SCRIPTS_DIR / f"{stem}.py"
    module_name = f"test_{stem}_{len(sys.modules)}"
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FakeParser:
    def __init__(self, namespace: SimpleNamespace) -> None:
        self._namespace = namespace

    def parse_args(self) -> SimpleNamespace:
        return self._namespace


@pytest.mark.parametrize(
    ("stem", "attribute"),
    [
        ("assessment_publish_gate", "decide_gate"),
        ("check_code_shape", "main"),
        ("check_docs_freshness", "main"),
        ("check_pr_closure_state", "main"),
        ("check_pr_review_gate", "main"),
        ("release_gate_runtime", "main"),
        ("seed_trends", "seed_trends"),
        ("sync_automations", "main"),
        ("validate_assessment_artifacts", "validate_file"),
    ],
)
def test_script_modules_import_without_executing_main(stem: str, attribute: str) -> None:
    module = _load_script_module(stem)
    assert hasattr(module, attribute)


def test_check_docs_freshness_main_passes_and_renders_lines(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module("check_docs_freshness")
    namespace = SimpleNamespace(
        repo_root=".",
        override_file="docs/DOCS_FRESHNESS_OVERRIDES.json",
        max_age_days=0,
        fail_on_warnings=False,
        planning_artifact=[],
    )
    monkeypatch.setattr(module, "_build_parser", lambda: _FakeParser(namespace))
    monkeypatch.setattr(
        module,
        "run_docs_freshness_check",
        lambda **_: SimpleNamespace(errors=[], warnings=[]),
    )
    monkeypatch.setattr(module, "render_docs_freshness_issues", lambda _result: ["warn-only line"])

    result = module.main()

    assert result == 0
    assert capsys.readouterr().out.splitlines() == [
        "warn-only line",
        "Docs freshness check passed.",
    ]


def test_check_docs_freshness_main_fails_for_errors_and_warnings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module("check_docs_freshness")
    namespace = SimpleNamespace(
        repo_root=".",
        override_file="docs/DOCS_FRESHNESS_OVERRIDES.json",
        max_age_days=45,
        fail_on_warnings=True,
        planning_artifact=["tasks/exec_plans/TASK-351.md"],
    )
    monkeypatch.setattr(module, "_build_parser", lambda: _FakeParser(namespace))

    monkeypatch.setattr(
        module,
        "run_docs_freshness_check",
        lambda **_: SimpleNamespace(errors=["err"], warnings=[]),
    )
    monkeypatch.setattr(module, "render_docs_freshness_issues", lambda _result: ["error line"])
    assert module.main() == 2
    assert capsys.readouterr().out.splitlines() == ["error line"]

    monkeypatch.setattr(
        module,
        "run_docs_freshness_check",
        lambda **_: SimpleNamespace(errors=[], warnings=["warn"]),
    )
    monkeypatch.setattr(module, "render_docs_freshness_issues", lambda _result: ["warning line"])
    assert module.main() == 2
    assert capsys.readouterr().out.splitlines() == [
        "warning line",
        "Failing due to --fail-on-warnings.",
    ]


def test_release_gate_runtime_main_handles_missing_input_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module("release_gate_runtime")
    missing_path = tmp_path / "missing.json"

    strict_namespace = SimpleNamespace(
        input=str(missing_path),
        environment="production",
        strict=False,
        max_error_rate=0.05,
        max_p95_latency_ms=1200.0,
        max_budget_denial_rate=0.10,
        max_production_error_rate_drift=0.02,
        min_window_minutes=60,
    )
    monkeypatch.setattr(module, "_build_parser", lambda: _FakeParser(strict_namespace))
    assert module.main() == 2
    assert "FAIL runtime metrics input not found" in capsys.readouterr().out

    warn_namespace = SimpleNamespace(**{**strict_namespace.__dict__, "environment": "development"})
    monkeypatch.setattr(module, "_build_parser", lambda: _FakeParser(warn_namespace))
    assert module.main() == 0
    assert "WARN runtime metrics input not found" in capsys.readouterr().out


def test_release_gate_runtime_main_handles_invalid_payload_and_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module("release_gate_runtime")
    input_path = tmp_path / "runtime.json"
    input_path.write_text("not-json", encoding="utf-8")
    invalid_namespace = SimpleNamespace(
        input=str(input_path),
        environment="staging",
        strict=False,
        max_error_rate=-1.0,
        max_p95_latency_ms=0.0,
        max_budget_denial_rate=2.0,
        max_production_error_rate_drift=-5.0,
        min_window_minutes=0,
    )
    monkeypatch.setattr(module, "_build_parser", lambda: _FakeParser(invalid_namespace))
    assert module.main() == 2
    assert "FAIL invalid JSON" in capsys.readouterr().out

    input_path.write_text(json.dumps({"stages": {}}), encoding="utf-8")
    monkeypatch.setattr(
        module,
        "parse_stage_metrics",
        lambda _payload: (_ for _ in ()).throw(ValueError("bad metrics")),
    )
    assert module.main() == 2
    assert capsys.readouterr().out.splitlines() == ["FAIL bad metrics"]

    fake_check = SimpleNamespace(
        status="PASS",
        stage="production",
        metric="error_rate",
        observed=0.01,
        threshold=0.05,
        message="healthy",
    )
    monkeypatch.setattr(module, "parse_stage_metrics", lambda _payload: {"production": object()})
    monkeypatch.setattr(
        module,
        "evaluate_runtime_gate",
        lambda **_: SimpleNamespace(checks=[fake_check], has_failures=False),
    )
    assert module.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "PASS production.error_rate observed=0.0100 threshold=0.0500 (healthy)"
    ]

    monkeypatch.setattr(
        module,
        "evaluate_runtime_gate",
        lambda **_: SimpleNamespace(checks=[fake_check], has_failures=True),
    )
    assert module.main() == 2
