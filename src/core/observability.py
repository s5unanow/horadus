"""
Prometheus metrics registry and helper recorders.
"""

from __future__ import annotations

from collections import defaultdict

from prometheus_client import Counter, Gauge

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
SOURCE_FRESHNESS_STALE_TOTAL = Counter(
    "source_freshness_stale_total",
    "Stale source detections by collector type.",
    ["collector"],
)
SOURCE_CATCHUP_DISPATCH_TOTAL = Counter(
    "source_catchup_dispatch_total",
    "Catch-up collector dispatches triggered by freshness checks.",
    ["collector"],
)
PROCESSING_BACKLOG_DEPTH = Gauge(
    "processing_backlog_depth",
    "Current pending raw-item backlog depth observed during dispatch planning.",
)
PROCESSING_DISPATCH_DECISIONS_TOTAL = Counter(
    "processing_dispatch_decisions_total",
    "Processing dispatch decisions by outcome and reason.",
    ["decision", "reason"],
)
PROCESSING_INGESTED_LANGUAGE_TOTAL = Counter(
    "processing_ingested_language_total",
    "Processed raw-item intake counts segmented by language code.",
    ["language"],
)
PROCESSING_TIER1_LANGUAGE_OUTCOME_TOTAL = Counter(
    "processing_tier1_language_outcome_total",
    "Tier-1 routing outcomes segmented by language code.",
    ["language", "outcome"],
)
PROCESSING_TIER2_LANGUAGE_USAGE_TOTAL = Counter(
    "processing_tier2_language_usage_total",
    "Tier-2 classification usage segmented by language code.",
    ["language"],
)
LLM_SEMANTIC_CACHE_LOOKUPS_TOTAL = Counter(
    "llm_semantic_cache_lookups_total",
    "LLM semantic cache lookups by stage and result.",
    ["stage", "result"],
)
TAXONOMY_GAPS_TOTAL = Counter(
    "taxonomy_gaps_total",
    "Captured taxonomy-gap records by reason.",
    ["reason"],
)
TAXONOMY_GAP_SIGNAL_KEYS_TOTAL = Counter(
    "taxonomy_gap_signal_keys_total",
    "Unknown signal-type taxonomy gaps by trend_id and signal_type.",
    ["trend_id", "signal_type"],
)
PROCESSING_CORROBORATION_PATH_TOTAL = Counter(
    "processing_corroboration_path_total",
    "Corroboration scoring path usage by mode and reason.",
    ["mode", "reason"],
)
PROCESSING_EVENT_SUPPRESSIONS_TOTAL = Counter(
    "processing_event_suppressions_total",
    "Event suppressions applied during processing by action and stage.",
    ["action", "stage"],
)
EMBEDDING_INPUTS_TOTAL = Counter(
    "embedding_inputs_total",
    "Total embedding inputs observed before provider submission.",
    ["entity_type"],
)
EMBEDDING_INPUTS_TRUNCATED_TOTAL = Counter(
    "embedding_inputs_truncated_total",
    "Embedding inputs that exceeded token budget and required truncation/chunking.",
    ["entity_type", "strategy"],
)
EMBEDDING_TAIL_TOKENS_DROPPED_TOTAL = Counter(
    "embedding_tail_tokens_dropped_total",
    "Approximate embedding tail tokens dropped by truncation policy.",
    ["entity_type", "strategy"],
)
EMBEDDING_INPUT_TRUNCATION_RATIO = Gauge(
    "embedding_input_truncation_ratio",
    "Rolling in-process ratio of embedding inputs that required truncation/chunking.",
    ["entity_type"],
)
RETENTION_CLEANUP_ROWS_TOTAL = Counter(
    "retention_cleanup_rows_total",
    "Retention cleanup row counts by table/action/mode.",
    ["table", "action", "mode"],
)
RETENTION_CLEANUP_RUNS_TOTAL = Counter(
    "retention_cleanup_runs_total",
    "Retention cleanup run outcomes by mode and status.",
    ["mode", "status"],
)

_EMBEDDING_TOTAL_BY_ENTITY: dict[str, int] = defaultdict(int)
_EMBEDDING_TRUNCATED_BY_ENTITY: dict[str, int] = defaultdict(int)


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


def record_source_freshness_stale(*, collector: str, stale_count: int) -> None:
    SOURCE_FRESHNESS_STALE_TOTAL.labels(collector=collector).inc(max(0, stale_count))


def record_source_catchup_dispatch(*, collector: str) -> None:
    SOURCE_CATCHUP_DISPATCH_TOTAL.labels(collector=collector).inc()


def record_llm_semantic_cache_lookup(*, stage: str, result: str) -> None:
    LLM_SEMANTIC_CACHE_LOOKUPS_TOTAL.labels(stage=stage, result=result).inc()


def record_processing_backlog_depth(*, pending_count: int) -> None:
    PROCESSING_BACKLOG_DEPTH.set(max(0, pending_count))


def record_processing_dispatch_decision(*, dispatched: bool, reason: str) -> None:
    decision = "dispatched" if dispatched else "throttled"
    normalized_reason = reason.strip() or "unspecified"
    PROCESSING_DISPATCH_DECISIONS_TOTAL.labels(
        decision=decision,
        reason=normalized_reason,
    ).inc()


def record_processing_ingested_language(*, language: str) -> None:
    PROCESSING_INGESTED_LANGUAGE_TOTAL.labels(language=language).inc()


def record_processing_tier1_language_outcome(*, language: str, outcome: str) -> None:
    normalized_outcome = outcome.strip() or "unknown"
    PROCESSING_TIER1_LANGUAGE_OUTCOME_TOTAL.labels(
        language=language,
        outcome=normalized_outcome,
    ).inc()


def record_processing_tier2_language_usage(*, language: str) -> None:
    PROCESSING_TIER2_LANGUAGE_USAGE_TOTAL.labels(language=language).inc()


def record_taxonomy_gap(*, reason: str, trend_id: str, signal_type: str) -> None:
    normalized_reason = reason.strip() or "unknown"
    TAXONOMY_GAPS_TOTAL.labels(reason=normalized_reason).inc()
    if normalized_reason == "unknown_signal_type":
        TAXONOMY_GAP_SIGNAL_KEYS_TOTAL.labels(
            trend_id=trend_id.strip() or "unknown",
            signal_type=signal_type.strip() or "unknown",
        ).inc()


def record_processing_corroboration_path(*, mode: str, reason: str) -> None:
    normalized_mode = mode.strip() or "unknown"
    normalized_reason = reason.strip() or "unspecified"
    PROCESSING_CORROBORATION_PATH_TOTAL.labels(
        mode=normalized_mode,
        reason=normalized_reason,
    ).inc()


def record_processing_event_suppression(*, action: str, stage: str) -> None:
    normalized_action = action.strip() or "unknown"
    normalized_stage = stage.strip() or "unknown"
    PROCESSING_EVENT_SUPPRESSIONS_TOTAL.labels(
        action=normalized_action,
        stage=normalized_stage,
    ).inc()


def record_embedding_input_guardrail(
    *,
    entity_type: str,
    strategy: str,
    was_cut: bool,
    dropped_tail_tokens: int,
) -> None:
    normalized_entity = entity_type.strip() or "unknown"
    normalized_strategy = strategy.strip() or "none"

    EMBEDDING_INPUTS_TOTAL.labels(entity_type=normalized_entity).inc()
    _EMBEDDING_TOTAL_BY_ENTITY[normalized_entity] += 1

    if was_cut:
        EMBEDDING_INPUTS_TRUNCATED_TOTAL.labels(
            entity_type=normalized_entity,
            strategy=normalized_strategy,
        ).inc()
        _EMBEDDING_TRUNCATED_BY_ENTITY[normalized_entity] += 1

        EMBEDDING_TAIL_TOKENS_DROPPED_TOTAL.labels(
            entity_type=normalized_entity,
            strategy=normalized_strategy,
        ).inc(max(0, int(dropped_tail_tokens)))

    total = _EMBEDDING_TOTAL_BY_ENTITY[normalized_entity]
    truncated = _EMBEDDING_TRUNCATED_BY_ENTITY[normalized_entity]
    EMBEDDING_INPUT_TRUNCATION_RATIO.labels(entity_type=normalized_entity).set(
        (truncated / total) if total else 0.0
    )


def record_retention_cleanup_rows(*, table: str, action: str, dry_run: bool, count: int) -> None:
    RETENTION_CLEANUP_ROWS_TOTAL.labels(
        table=table.strip() or "unknown",
        action=action.strip() or "unknown",
        mode="dry_run" if dry_run else "delete",
    ).inc(max(0, int(count)))


def record_retention_cleanup_run(*, dry_run: bool, status: str) -> None:
    RETENTION_CLEANUP_RUNS_TOTAL.labels(
        mode="dry_run" if dry_run else "delete",
        status=status.strip() or "unknown",
    ).inc()
