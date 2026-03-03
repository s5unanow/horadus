"""Cross-stage runtime SLO/error-budget release gate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StageName = Literal["development", "staging", "production"]


@dataclass(frozen=True, slots=True)
class StageRuntimeMetrics:
    error_rate: float
    p95_latency_ms: float
    budget_denial_rate: float
    window_minutes: int


@dataclass(frozen=True, slots=True)
class RuntimeGateThresholds:
    max_error_rate: float
    max_p95_latency_ms: float
    max_budget_denial_rate: float
    max_production_error_rate_drift: float
    min_window_minutes: int


@dataclass(frozen=True, slots=True)
class RuntimeGateCheck:
    stage: str
    metric: str
    status: str
    observed: float
    threshold: float
    message: str


@dataclass(frozen=True, slots=True)
class RuntimeGateResult:
    strict_mode: bool
    checks: tuple[RuntimeGateCheck, ...]

    @property
    def has_failures(self) -> bool:
        return any(check.status == "FAIL" for check in self.checks)


def _coerce_rate(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def evaluate_runtime_gate(
    *,
    metrics_by_stage: dict[str, StageRuntimeMetrics],
    thresholds: RuntimeGateThresholds,
    strict_mode: bool,
) -> RuntimeGateResult:
    checks: list[RuntimeGateCheck] = []

    for stage in ("development", "staging", "production"):
        metrics = metrics_by_stage.get(stage)
        if metrics is None:
            if strict_mode and stage in {"staging", "production"}:
                checks.append(
                    RuntimeGateCheck(
                        stage=stage,
                        metric="metrics_present",
                        status="FAIL",
                        observed=0.0,
                        threshold=1.0,
                        message="missing stage metrics",
                    )
                )
            continue

        stage_checks: list[RuntimeGateCheck] = [
            RuntimeGateCheck(
                stage=stage,
                metric="window_minutes",
                status=(
                    "PASS" if metrics.window_minutes >= thresholds.min_window_minutes else "FAIL"
                ),
                observed=float(metrics.window_minutes),
                threshold=float(thresholds.min_window_minutes),
                message="window length check",
            ),
            RuntimeGateCheck(
                stage=stage,
                metric="error_rate",
                status=("PASS" if metrics.error_rate <= thresholds.max_error_rate else "FAIL"),
                observed=metrics.error_rate,
                threshold=thresholds.max_error_rate,
                message="API/worker error-rate SLO",
            ),
            RuntimeGateCheck(
                stage=stage,
                metric="p95_latency_ms",
                status=(
                    "PASS" if metrics.p95_latency_ms <= thresholds.max_p95_latency_ms else "FAIL"
                ),
                observed=metrics.p95_latency_ms,
                threshold=thresholds.max_p95_latency_ms,
                message="p95 latency SLO",
            ),
            RuntimeGateCheck(
                stage=stage,
                metric="budget_denial_rate",
                status=(
                    "PASS"
                    if metrics.budget_denial_rate <= thresholds.max_budget_denial_rate
                    else "FAIL"
                ),
                observed=metrics.budget_denial_rate,
                threshold=thresholds.max_budget_denial_rate,
                message="error-budget proxy (budget denials)",
            ),
        ]
        checks.extend(stage_checks)

    if "production" in metrics_by_stage and "staging" in metrics_by_stage:
        production_error_rate = metrics_by_stage["production"].error_rate
        staging_error_rate = metrics_by_stage["staging"].error_rate
        drift = production_error_rate - staging_error_rate
        checks.append(
            RuntimeGateCheck(
                stage="cross-stage",
                metric="production_error_rate_drift",
                status=("PASS" if drift <= thresholds.max_production_error_rate_drift else "FAIL"),
                observed=drift,
                threshold=thresholds.max_production_error_rate_drift,
                message="production error rate vs staging drift",
            )
        )

    if not strict_mode:
        relaxed: list[RuntimeGateCheck] = []
        for check in checks:
            if check.status == "FAIL":
                relaxed.append(
                    RuntimeGateCheck(
                        stage=check.stage,
                        metric=check.metric,
                        status="WARN",
                        observed=check.observed,
                        threshold=check.threshold,
                        message=check.message,
                    )
                )
            else:
                relaxed.append(check)
        checks = relaxed

    return RuntimeGateResult(
        strict_mode=strict_mode,
        checks=tuple(checks),
    )


def parse_stage_metrics(payload: dict[str, object]) -> dict[str, StageRuntimeMetrics]:
    stages_raw = payload.get("stages") if isinstance(payload.get("stages"), dict) else payload
    if not isinstance(stages_raw, dict):
        msg = "runtime gate payload must be an object keyed by stage name"
        raise ValueError(msg)

    parsed: dict[str, StageRuntimeMetrics] = {}
    for stage_name, raw_metrics in stages_raw.items():
        normalized_stage = str(stage_name).strip().lower()
        if normalized_stage not in {"development", "staging", "production"}:
            continue
        if not isinstance(raw_metrics, dict):
            continue

        error_rate = _coerce_rate(float(raw_metrics.get("error_rate", 0.0)))
        p95_latency_ms = max(0.0, float(raw_metrics.get("p95_latency_ms", 0.0)))
        budget_denial_rate = _coerce_rate(float(raw_metrics.get("budget_denial_rate", 0.0)))
        window_minutes = max(0, int(raw_metrics.get("window_minutes", 0)))

        parsed[normalized_stage] = StageRuntimeMetrics(
            error_rate=error_rate,
            p95_latency_ms=p95_latency_ms,
            budget_denial_rate=budget_denial_rate,
            window_minutes=window_minutes,
        )

    return parsed
