"""
Prometheus metrics registry and helper recorders.
"""

from __future__ import annotations

from prometheus_client import Counter

INGESTION_ITEMS_TOTAL = Counter(
    "ingestion_items_total",
    "Ingestion item counts by collector and status.",
    ["collector", "status"],
)
LLM_API_CALLS_TOTAL = Counter(
    "llm_api_calls_total",
    "LLM API call counts by stage.",
    ["stage"],
)
LLM_ESTIMATED_COST_USD_TOTAL = Counter(
    "llm_estimated_cost_usd_total",
    "Estimated LLM cost in USD by stage.",
    ["stage"],
)
WORKER_ERRORS_TOTAL = Counter(
    "worker_errors_total",
    "Worker task failures by task name.",
    ["task_name"],
)
LLM_BUDGET_DENIALS_TOTAL = Counter(
    "llm_budget_denials_total",
    "Budget enforcement denials by tier and reason.",
    ["tier", "reason"],
)
CALIBRATION_DRIFT_ALERTS_TOTAL = Counter(
    "calibration_drift_alerts_total",
    "Calibration drift alerts by alert type and severity.",
    ["alert_type", "severity"],
)
PROCESSING_REAPER_RESETS_TOTAL = Counter(
    "processing_reaper_resets_total",
    "Count of raw items reset from processing to pending by stale-item reaper.",
)


def record_collector_metrics(
    *,
    collector: str,
    fetched: int,
    stored: int,
    skipped: int,
    errors: int,
) -> None:
    INGESTION_ITEMS_TOTAL.labels(collector=collector, status="fetched").inc(max(0, fetched))
    INGESTION_ITEMS_TOTAL.labels(collector=collector, status="stored").inc(max(0, stored))
    INGESTION_ITEMS_TOTAL.labels(collector=collector, status="skipped").inc(max(0, skipped))
    INGESTION_ITEMS_TOTAL.labels(collector=collector, status="errors").inc(max(0, errors))


def record_pipeline_metrics(run_result: dict[str, int | float | str]) -> None:
    tier1_calls = int(run_result.get("tier1_api_calls", 0))
    tier2_calls = int(run_result.get("tier2_api_calls", 0))
    embedding_calls = int(run_result.get("embedding_api_calls", 0))
    tier1_cost = float(run_result.get("tier1_estimated_cost_usd", 0.0))
    tier2_cost = float(run_result.get("tier2_estimated_cost_usd", 0.0))
    embedding_cost = float(run_result.get("embedding_estimated_cost_usd", 0.0))

    LLM_API_CALLS_TOTAL.labels(stage="tier1").inc(max(0, tier1_calls))
    LLM_API_CALLS_TOTAL.labels(stage="tier2").inc(max(0, tier2_calls))
    LLM_API_CALLS_TOTAL.labels(stage="embedding").inc(max(0, embedding_calls))

    LLM_ESTIMATED_COST_USD_TOTAL.labels(stage="tier1").inc(max(0.0, tier1_cost))
    LLM_ESTIMATED_COST_USD_TOTAL.labels(stage="tier2").inc(max(0.0, tier2_cost))
    LLM_ESTIMATED_COST_USD_TOTAL.labels(stage="embedding").inc(max(0.0, embedding_cost))


def record_worker_error(task_name: str) -> None:
    WORKER_ERRORS_TOTAL.labels(task_name=task_name).inc()


def record_budget_denial(*, tier: str, reason: str) -> None:
    LLM_BUDGET_DENIALS_TOTAL.labels(tier=tier, reason=reason).inc()


def record_calibration_drift_alert(*, alert_type: str, severity: str) -> None:
    CALIBRATION_DRIFT_ALERTS_TOTAL.labels(
        alert_type=alert_type,
        severity=severity,
    ).inc()


def record_processing_reaper_resets(*, reset_count: int) -> None:
    PROCESSING_REAPER_RESETS_TOTAL.inc(max(0, reset_count))
