from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import tools.horadus.python.horadus_cli.task_workflow_core as task_commands_module
from tests.horadus_cli.v2.helpers import _completed

pytestmark = pytest.mark.unit


def test_full_local_gate_steps_match_expected_ci_parity_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UV_BIN", raising=False)

    steps = task_commands_module.full_local_gate_steps()

    assert [step.name for step in steps] == [
        "check-tracked-artifacts",
        "docs-freshness",
        "code-shape",
        "ruff-format-check",
        "ruff-check",
        "mypy",
        "validate-taxonomy",
        "audit-eval",
        "pytest-unit-cov",
        "secret-scan",
        "bandit",
        "dependency-audit",
        "lockfile-check",
        "integration-docker",
        "build-package",
    ]
    assert steps[0].command == "./scripts/check_no_tracked_artifacts.sh"
    assert steps[1].command == "uv run --no-sync python scripts/check_docs_freshness.py"
    assert steps[2].command == "uv run --no-sync python scripts/check_code_shape.py"
    assert steps[3].command == "uv run --no-sync ruff format src/ tools/ scripts/ tests/ --check"
    assert steps[4].command == "uv run --no-sync ruff check src/ tools/ scripts/ tests/"
    assert steps[5].command == "uv run --no-sync mypy src/ tools/horadus/python scripts"
    assert steps[6].command.startswith("uv run --no-sync horadus eval validate-taxonomy ")
    assert steps[7].command == (
        "uv run --no-sync horadus eval audit --gold-set ai/eval/gold_set.jsonl "
        "--output-dir ai/eval/results --max-items 0 --fail-on-warnings"
    )
    assert steps[8].command == "./scripts/run_unit_coverage_gate.sh"
    assert steps[9].command == "./scripts/run_secret_scan.sh"
    assert steps[10].command == (
        "uv run --no-sync bandit -c pyproject.toml -r src/ tools/horadus/python scripts"
    )
    assert steps[11].command == "./scripts/run_dependency_audit.sh"
    assert steps[13].command == "./scripts/test_integration_docker.sh"
    assert steps[14].command == (
        "rm -rf dist build *.egg-info && "
        "uv run --no-sync python -m build --no-isolation && "
        "uv run --no-sync twine check dist/*"
    )


def test_repo_workflow_configs_enforce_hard_unit_coverage_threshold() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    precommit = (repo_root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    ci_workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")

    assert "./scripts/run_unit_coverage_gate.sh" in precommit
    assert "stages: [pre-push]" in precommit
    assert "./scripts/run_unit_coverage_gate.sh" in ci_workflow
    assert "--cov=scripts" in ci_workflow
    assert "--cov-config=pyproject.toml" in ci_workflow
    assert "python scripts/check_code_shape.py" in ci_workflow
    assert "--cov-fail-under=100" in ci_workflow
    assert "--cov=scripts" in makefile
    assert "--cov-config=pyproject.toml" in makefile
    assert "code-shape: deps-dev" in makefile
    assert "python scripts/check_code_shape.py" in makefile
    assert "test-unit-cov: deps-dev" in makefile
    assert "./scripts/run_unit_coverage_gate.sh" in makefile
    assert 'source = ["src", "tools", "scripts"]' in pyproject
    assert 'patch = ["subprocess"]' in pyproject


def test_repo_workflow_configs_include_repo_owned_security_scans() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    precommit = (repo_root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    ci_workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")

    assert "--baseline, .secrets.baseline, --no-verify" in precommit
    assert "./scripts/run_secret_scan.sh" in ci_workflow
    assert "./scripts/run_dependency_audit.sh" in ci_workflow
    assert "bandit -c pyproject.toml -r src/ tools/horadus/python scripts" in ci_workflow
    assert "secret-scan: deps-dev" in makefile
    assert "./scripts/run_secret_scan.sh" in makefile
    assert "dependency-audit: deps-dev" in makefile
    assert "./scripts/run_dependency_audit.sh" in makefile
    assert "bandit -c pyproject.toml -r src/ tools/horadus/python scripts" in makefile


def test_repo_workflow_configs_include_repo_owned_artifact_validation() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    ci_workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")

    assert (
        "validate-assessments: ## Validate artifacts/assessments/ against minimal schema"
        in makefile
    )
    assert "python scripts/validate_assessment_artifacts.py" in makefile
    assert (
        "horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir "
        "ai/eval/results --max-items 0 --fail-on-warnings" in makefile
    )
    assert "horadus eval audit \\" in ci_workflow
    assert "--fail-on-warnings" in ci_workflow
    assert "Validate assessment artifacts" not in ci_workflow


def test_release_gate_reuses_canonical_full_local_gate() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")

    assert (
        "release-gate: deps-dev ## Run the canonical full local gate plus release-only migration validation"
        in makefile
    )
    assert (
        "@MIGRATION_GATE_VALIDATE_AUTOGEN=true $(UV_RUN) horadus tasks local-gate --full"
        in makefile
    )
    assert (
        '@$(MAKE) db-migration-gate MIGRATION_GATE_DATABASE_URL="$(RELEASE_GATE_DATABASE_URL)" MIGRATION_GATE_VALIDATE_AUTOGEN="$(MIGRATION_GATE_VALIDATE_AUTOGEN)"'
        in makefile
    )
    assert "RELEASE_GATE_INCLUDE_EVAL" not in makefile


def test_local_gate_data_dry_run_reports_custom_absolute_uv_bin_for_build_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_uv = "/tmp/custom-tools/uv"
    monkeypatch.setenv("UV_BIN", custom_uv)
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_command_available",
        lambda name: name if name == custom_uv else None,
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    build_step = next(step for step in data["steps"] if step["name"] == "build-package")
    assert build_step["command"] == (
        "rm -rf dist build *.egg-info && "
        f"{custom_uv} run --no-sync python -m build --no-isolation && "
        f"{custom_uv} run --no-sync twine check dist/*"
    )
    assert f"- build-package: {build_step['command']}" in lines


def test_repo_workflow_build_tooling_runs_from_locked_dev_environment() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    ci_workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")

    assert "uv sync --extra dev --frozen" in ci_workflow
    assert "uv run --no-sync python -m build --no-isolation" in ci_workflow
    assert "uv run --no-sync twine check dist/*" in ci_workflow
    assert '"build>=' in pyproject
    assert '"twine>=' in pyproject
    assert '"hatchling>=' in pyproject


def test_local_gate_data_requires_full_mode() -> None:
    exit_code, data, lines = task_commands_module.local_gate_data(full=False, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.VALIDATION_ERROR
    assert data == {"full": False}
    assert lines[-1] == (
        "Use `horadus tasks local-gate --full` for the canonical post-task local gate."
    )


def test_local_gate_data_reports_missing_uv_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module, "_ensure_command_available", lambda _name: None)

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["missing_command"] == "uv"
    assert lines == ["Local gate failed: uv is required to run the canonical full local gate."]


def test_ensure_docker_ready_returns_immediately_when_daemon_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], stdout="Server Version: test\n"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is True
    assert result.attempted_start is False
    assert result.lines == ["Docker is ready for integration gate."]


def test_ensure_docker_ready_attempts_auto_start_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    info_results = iter(
        [
            _completed(["docker", "info"], returncode=1, stderr="daemon down"),
            _completed(["docker", "info"], stdout="Server Version: test\n"),
        ]
    )
    monkeypatch.setattr(task_commands_module, "_docker_info_result", lambda: next(info_results))
    start_calls: list[str] = []
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: (
            start_calls.append(command) or _completed(["bash", "-lc", command], stdout="started\n")
        ),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert start_calls == ["echo starting-docker"]
    assert result.ready is True
    assert result.attempted_start is True
    assert result.lines[-1] == "Docker became ready after auto-start."


def test_ensure_docker_ready_reports_unsupported_auto_start_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.sys, "platform", "linux")

    def fake_which(name: str) -> str | None:
        if name == "docker":
            return "/bin/docker"
        return None

    monkeypatch.setattr(task_commands_module, "_ensure_command_available", fake_which)
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], returncode=1, stderr="daemon down"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.supported_auto_start is False
    assert result.lines[-1] == (
        "Auto-start is unsupported on this environment; start Docker manually and retry."
    )


def test_ensure_docker_ready_reports_invalid_env_override_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setenv("DOCKER_READY_TIMEOUT_SECONDS", "not-an-int")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], returncode=1, stderr="daemon down"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.attempted_start is False
    assert result.lines == [
        "Docker readiness failed: DOCKER_READY_TIMEOUT_SECONDS must be an integer."
    ]


def test_ensure_docker_ready_reports_missing_docker_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_which = shutil.which

    def fake_which(name: str) -> str | None:
        if name == "docker":
            return None
        return original_which(name)

    monkeypatch.setattr(task_commands_module, "_ensure_command_available", fake_which)

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.lines == ["Docker readiness failed: docker CLI is required for integration gate."]


def test_ensure_docker_ready_reports_auto_start_command_failure_via_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_commands_module.sys, "platform", "linux")

    def fake_which(name: str) -> str | None:
        if name in {"docker", "docker-desktop"}:
            return f"/bin/{name}"
        return None

    monkeypatch.setattr(task_commands_module, "_ensure_command_available", fake_which)
    monkeypatch.setattr(
        task_commands_module,
        "_docker_info_result",
        lambda: _completed(["docker", "info"], returncode=1, stderr="daemon down"),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="start failed"),
    )

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.attempted_start is True
    assert result.lines[-2:] == ["Docker auto-start command failed.", "start failed"]


def test_docker_helper_functions_cover_macos_auto_start_and_timeout_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HORADUS_DOCKER_START_CMD", raising=False)
    monkeypatch.setattr(task_commands_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        task_commands_module,
        "_ensure_command_available",
        lambda name: "/usr/bin/open" if name in {"docker", "open"} else None,
    )

    plan = task_commands_module._docker_start_plan()
    assert plan is not None
    assert plan.argv == ["open", "-a", "Docker"]

    run_calls: list[list[str]] = []
    monkeypatch.setattr(
        task_commands_module,
        "_run_command",
        lambda args, **_kwargs: run_calls.append(args) or _completed(args, stdout="docker ok\n"),
    )
    info_result = task_commands_module._docker_info_result()
    assert info_result.stdout == "docker ok\n"
    assert run_calls == [["docker", "info"]]

    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setenv("DOCKER_READY_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DOCKER_READY_POLL_SECONDS", "2")
    info_results = iter(
        [
            _completed(["docker", "info"], returncode=1, stderr="daemon down"),
            _completed(["docker", "info"], returncode=1, stderr="still down"),
            _completed(["docker", "info"], returncode=1, stderr="still down"),
        ]
    )
    time_values = iter([0.0, 0.5, 1.5])
    sleep_calls: list[int] = []
    monkeypatch.setattr(task_commands_module, "_docker_info_result", lambda: next(info_results))
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: _completed(["bash", "-lc", command], stdout="started\n"),
    )
    monkeypatch.setattr(task_commands_module.time, "time", lambda: next(time_values))
    monkeypatch.setattr(task_commands_module.time, "sleep", sleep_calls.append)

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is False
    assert result.attempted_start is True
    assert result.lines[-2:] == [
        "Docker auto-start did not make the daemon ready before timeout.",
        "still down",
    ]
    assert sleep_calls == [2]


def test_ensure_docker_ready_retries_without_sleep_when_polling_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HORADUS_DOCKER_START_CMD", "echo starting-docker")
    monkeypatch.setenv("DOCKER_READY_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DOCKER_READY_POLL_SECONDS", "0")
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    info_results = iter(
        [
            _completed(["docker", "info"], returncode=1, stderr="daemon down"),
            _completed(["docker", "info"], returncode=1, stderr="still down"),
            _completed(["docker", "info"], stdout="Server Version: test\n"),
        ]
    )
    time_values = iter([0.0, 0.5, 0.6])
    monkeypatch.setattr(task_commands_module, "_docker_info_result", lambda: next(info_results))
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: _completed(["bash", "-lc", command], stdout="started\n"),
    )
    monkeypatch.setattr(task_commands_module.time, "time", lambda: next(time_values))

    result = task_commands_module.ensure_docker_ready(reason="integration gate")

    assert result.ready is True
    assert result.attempted_start is True
    assert result.lines[-1] == "Docker became ready after auto-start."


def test_local_gate_data_dry_run_reports_canonical_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(name="docs-freshness", command="uv run docs"),
            task_commands_module.LocalGateStep(name="ruff-check", command="uv run ruff"),
        ],
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=True)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["mode"] == "full"
    assert data["dry_run"] is True
    assert lines == [
        "Running canonical full local gate:",
        "- docs-freshness: uv run docs",
        "- ruff-check: uv run ruff",
        "Dry run: validated the canonical step list without executing it.",
    ]


def test_local_gate_data_runs_all_steps_and_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(name="docs-freshness", command="step-1"),
            task_commands_module.LocalGateStep(name="ruff-check", command="step-2"),
        ],
    )
    calls: list[str] = []

    def fake_run_shell(command: str) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed(["bash", "-lc", command], stdout=f"ok:{command}\n")

    monkeypatch.setattr(task_commands_module, "_run_shell", fake_run_shell)

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert calls == ["step-1", "step-2"]
    assert data["mode"] == "full"
    assert lines == [
        "Running canonical full local gate:",
        "[1/2] RUN docs-freshness",
        "[1/2] PASS docs-freshness",
        "[2/2] RUN ruff-check",
        "[2/2] PASS ruff-check",
        "Full local gate passed.",
    ]


def test_local_gate_data_checks_docker_readiness_before_integration_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(name="docs-freshness", command="step-1"),
            task_commands_module.LocalGateStep(
                name="integration-docker", command="./scripts/test_integration_docker.sh"
            ),
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=True,
            attempted_start=True,
            supported_auto_start=True,
            lines=["Docker became ready after auto-start."],
        ),
    )
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda command: _completed(["bash", "-lc", command], stdout=f"ok:{command}\n"),
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.OK
    assert data["mode"] == "full"
    assert "Docker became ready after auto-start." in lines
    assert "[2/2] PASS integration-docker" in lines


def test_local_gate_data_blocks_when_docker_cannot_be_made_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [
            task_commands_module.LocalGateStep(
                name="integration-docker", command="./scripts/test_integration_docker.sh"
            )
        ],
    )
    monkeypatch.setattr(
        task_commands_module,
        "ensure_docker_ready",
        lambda **_kwargs: task_commands_module.DockerReadiness(
            ready=False,
            attempted_start=True,
            supported_auto_start=True,
            lines=["Docker auto-start did not make the daemon ready before timeout."],
        ),
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["failed_step"] == "integration-docker"
    assert data["docker_ready"] is False
    assert lines[-1] == "Local gate failed because Docker is not ready for the integration step."


def test_local_gate_data_reports_failed_step_with_condensed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_commands_module, "_ensure_command_available", lambda _name: "/bin/fake"
    )
    monkeypatch.setattr(
        task_commands_module,
        "full_local_gate_steps",
        lambda: [task_commands_module.LocalGateStep(name="pytest-unit-cov", command="step-fail")],
    )
    noisy_output = "\n".join(f"line-{index}" for index in range(100))
    monkeypatch.setattr(
        task_commands_module,
        "_run_shell",
        lambda _command: _completed(
            ["bash", "-lc", "step-fail"], returncode=1, stdout=noisy_output
        ),
    )

    exit_code, data, lines = task_commands_module.local_gate_data(full=True, dry_run=False)

    assert exit_code == task_commands_module.ExitCode.ENVIRONMENT_ERROR
    assert data["failed_step"] == "pytest-unit-cov"
    assert lines[2] == "Local gate failed at step `pytest-unit-cov`."
    assert lines[3] == "Command: step-fail"
    assert "... (" in "\n".join(lines)
