from __future__ import annotations

import shlex
from dataclasses import dataclass

from tools.horadus.python.horadus_workflow import task_workflow_shared as shared


@dataclass(slots=True)
class LocalGateStep:
    name: str
    command: str


def _validate_taxonomy_gate_command(uv_bin: str) -> str:
    return (
        f"{uv_bin} run --no-sync horadus eval validate-taxonomy "
        "--gold-set ai/eval/gold_set.jsonl "
        "--trend-config-dir config/trends "
        "--output-dir ai/eval/results "
        "--max-items 200 "
        "--tier1-trend-mode subset "
        "--signal-type-mode warn "
        "--unknown-trend-mode warn"
    )


def _audit_eval_gate_command(uv_bin: str) -> str:
    return (
        f"{uv_bin} run --no-sync horadus eval audit "
        "--gold-set ai/eval/gold_set.jsonl "
        "--output-dir ai/eval/results "
        "--max-items 200 "
        "--fail-on-warnings"
    )


def full_local_gate_steps() -> list[LocalGateStep]:
    uv_bin = shlex.quote(shared.getenv("UV_BIN") or "uv")
    return [
        LocalGateStep(
            name="check-tracked-artifacts", command="./scripts/check_no_tracked_artifacts.sh"
        ),
        LocalGateStep(
            name="docs-freshness",
            command=f"{uv_bin} run --no-sync python scripts/check_docs_freshness.py",
        ),
        LocalGateStep(
            name="code-shape", command=f"{uv_bin} run --no-sync python scripts/check_code_shape.py"
        ),
        LocalGateStep(
            name="ruff-format-check",
            command=f"{uv_bin} run --no-sync ruff format src/ tools/ scripts/ tests/ --check",
        ),
        LocalGateStep(
            name="ruff-check",
            command=f"{uv_bin} run --no-sync ruff check src/ tools/ scripts/ tests/",
        ),
        LocalGateStep(
            name="mypy", command=f"{uv_bin} run --no-sync mypy src/ tools/horadus/python scripts"
        ),
        LocalGateStep(name="validate-taxonomy", command=_validate_taxonomy_gate_command(uv_bin)),
        LocalGateStep(name="audit-eval", command=_audit_eval_gate_command(uv_bin)),
        LocalGateStep(name="pytest-unit-cov", command="./scripts/run_unit_coverage_gate.sh"),
        LocalGateStep(name="secret-scan", command="./scripts/run_secret_scan.sh"),
        LocalGateStep(
            name="bandit",
            command=(
                f"{uv_bin} run --no-sync bandit -c pyproject.toml -r src/ "
                "tools/horadus/python scripts"
            ),
        ),
        LocalGateStep(name="dependency-audit", command="./scripts/run_dependency_audit.sh"),
        LocalGateStep(name="lockfile-check", command=f"{uv_bin} lock --check"),
        LocalGateStep(name="integration-docker", command="./scripts/test_integration_docker.sh"),
        LocalGateStep(
            name="build-package",
            command=(
                "rm -rf dist build *.egg-info && "
                f"{uv_bin} run --no-sync python -m build --no-isolation && "
                f"{uv_bin} run --no-sync twine check dist/*"
            ),
        ),
    ]


__all__ = ["LocalGateStep", "full_local_gate_steps"]
