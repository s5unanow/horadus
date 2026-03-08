from __future__ import annotations

from collections import defaultdict

from src.core import observability


class _FakeChild:
    def __init__(self) -> None:
        self.inc_calls: list[float | None] = []
        self.set_calls: list[float] = []

    def inc(self, value: float | None = None) -> None:
        self.inc_calls.append(value)

    def set(self, value: float) -> None:
        self.set_calls.append(value)


class _FakeMetric:
    def __init__(self) -> None:
        self.children: dict[tuple[tuple[str, str], ...], _FakeChild] = {}
        self.inc_calls: list[float | None] = []
        self.set_calls: list[float] = []

    def labels(self, **labels: str) -> _FakeChild:
        key = tuple(sorted(labels.items()))
        child = self.children.get(key)
        if child is None:
            child = _FakeChild()
            self.children[key] = child
        return child

    def inc(self, value: float | None = None) -> None:
        self.inc_calls.append(value)

    def set(self, value: float) -> None:
        self.set_calls.append(value)


def test_observability_recorders_cover_metric_paths(monkeypatch) -> None:
    ingestion = _FakeMetric()
    api_calls = _FakeMetric()
    cost = _FakeMetric()
    failovers = _FakeMetric()
    degraded = _FakeMetric()
    worker_errors = _FakeMetric()
    budget_denials = _FakeMetric()
    drift_alerts = _FakeMetric()
    reaper_resets = _FakeMetric()
    source_stale = _FakeMetric()
    catchup = _FakeMetric()
    semantic_cache = _FakeMetric()
    backlog = _FakeMetric()
    dispatch = _FakeMetric()
    ingested_language = _FakeMetric()
    tier1_language = _FakeMetric()
    tier2_language = _FakeMetric()
    taxonomy = _FakeMetric()
    taxonomy_signal = _FakeMetric()
    corroboration = _FakeMetric()
    suppressions = _FakeMetric()
    embedding_inputs = _FakeMetric()
    embedding_truncated = _FakeMetric()
    embedding_dropped = _FakeMetric()
    embedding_ratio = _FakeMetric()
    retention_rows = _FakeMetric()
    retention_runs = _FakeMetric()

    monkeypatch.setattr(observability, "INGESTION_ITEMS_TOTAL", ingestion)
    monkeypatch.setattr(observability, "LLM_API_CALLS_TOTAL", api_calls)
    monkeypatch.setattr(observability, "LLM_ESTIMATED_COST_USD_TOTAL", cost)
    monkeypatch.setattr(observability, "LLM_FAILOVERS_TOTAL", failovers)
    monkeypatch.setattr(observability, "LLM_DEGRADED_MODE", degraded)
    monkeypatch.setattr(observability, "WORKER_ERRORS_TOTAL", worker_errors)
    monkeypatch.setattr(observability, "LLM_BUDGET_DENIALS_TOTAL", budget_denials)
    monkeypatch.setattr(observability, "CALIBRATION_DRIFT_ALERTS_TOTAL", drift_alerts)
    monkeypatch.setattr(observability, "PROCESSING_REAPER_RESETS_TOTAL", reaper_resets)
    monkeypatch.setattr(observability, "SOURCE_FRESHNESS_STALE_TOTAL", source_stale)
    monkeypatch.setattr(observability, "SOURCE_CATCHUP_DISPATCH_TOTAL", catchup)
    monkeypatch.setattr(observability, "LLM_SEMANTIC_CACHE_LOOKUPS_TOTAL", semantic_cache)
    monkeypatch.setattr(observability, "PROCESSING_BACKLOG_DEPTH", backlog)
    monkeypatch.setattr(observability, "PROCESSING_DISPATCH_DECISIONS_TOTAL", dispatch)
    monkeypatch.setattr(observability, "PROCESSING_INGESTED_LANGUAGE_TOTAL", ingested_language)
    monkeypatch.setattr(observability, "PROCESSING_TIER1_LANGUAGE_OUTCOME_TOTAL", tier1_language)
    monkeypatch.setattr(observability, "PROCESSING_TIER2_LANGUAGE_USAGE_TOTAL", tier2_language)
    monkeypatch.setattr(observability, "TAXONOMY_GAPS_TOTAL", taxonomy)
    monkeypatch.setattr(observability, "TAXONOMY_GAP_SIGNAL_KEYS_TOTAL", taxonomy_signal)
    monkeypatch.setattr(observability, "PROCESSING_CORROBORATION_PATH_TOTAL", corroboration)
    monkeypatch.setattr(observability, "PROCESSING_EVENT_SUPPRESSIONS_TOTAL", suppressions)
    monkeypatch.setattr(observability, "EMBEDDING_INPUTS_TOTAL", embedding_inputs)
    monkeypatch.setattr(observability, "EMBEDDING_INPUTS_TRUNCATED_TOTAL", embedding_truncated)
    monkeypatch.setattr(observability, "EMBEDDING_TAIL_TOKENS_DROPPED_TOTAL", embedding_dropped)
    monkeypatch.setattr(observability, "EMBEDDING_INPUT_TRUNCATION_RATIO", embedding_ratio)
    monkeypatch.setattr(observability, "RETENTION_CLEANUP_ROWS_TOTAL", retention_rows)
    monkeypatch.setattr(observability, "RETENTION_CLEANUP_RUNS_TOTAL", retention_runs)
    monkeypatch.setattr(observability, "_EMBEDDING_TOTAL_BY_ENTITY", defaultdict(int))
    monkeypatch.setattr(observability, "_EMBEDDING_TRUNCATED_BY_ENTITY", defaultdict(int))

    observability.record_collector_metrics(
        collector="rss",
        fetched=2,
        stored=1,
        skipped=-2,
        errors=-1,
    )
    observability.record_pipeline_metrics(
        {
            "tier1_api_calls": 2,
            "tier2_api_calls": -1,
            "embedding_api_calls": 3,
            "tier1_estimated_cost_usd": 0.5,
            "tier2_estimated_cost_usd": -0.25,
            "embedding_estimated_cost_usd": 0.75,
        }
    )
    observability.record_llm_failover(stage=" ")
    observability.set_llm_degraded_mode(stage=" tier2 ", is_degraded=True)
    observability.record_worker_error("sync_task")
    observability.record_budget_denial(tier="tier2", reason="budget_exhausted")
    observability.record_calibration_drift_alert(
        alert_type="mean_brier_drift",
        severity="warning",
    )
    observability.record_processing_reaper_resets(reset_count=-3)
    observability.record_source_freshness_stale(collector="gdelt", stale_count=-4)
    observability.record_source_catchup_dispatch(collector="rss")
    observability.record_llm_semantic_cache_lookup(stage="tier1", result="hit")
    observability.record_processing_backlog_depth(pending_count=-5)
    observability.record_processing_dispatch_decision(dispatched=True, reason=" ")
    observability.record_processing_dispatch_decision(dispatched=False, reason="quota")
    observability.record_processing_ingested_language(language="en")
    observability.record_processing_tier1_language_outcome(language="bg", outcome=" ")
    observability.record_processing_tier2_language_usage(language="es")
    observability.record_taxonomy_gap(reason=" ", trend_id="trend-1", signal_type="impact")
    observability.record_taxonomy_gap(
        reason="unknown_signal_type",
        trend_id=" ",
        signal_type=" ",
    )
    observability.record_processing_corroboration_path(mode=" ", reason=" ")
    observability.record_processing_event_suppression(action=" ", stage=" ")
    observability.record_embedding_input_guardrail(
        entity_type="trend",
        strategy="truncate",
        was_cut=True,
        dropped_tail_tokens=-7,
    )
    observability.record_embedding_input_guardrail(
        entity_type=" ",
        strategy=" ",
        was_cut=False,
        dropped_tail_tokens=5,
    )
    observability.record_retention_cleanup_rows(
        table=" ",
        action=" ",
        dry_run=True,
        count=-2,
    )
    observability.record_retention_cleanup_run(dry_run=False, status=" ")

    assert ingestion.children[(("collector", "rss"), ("status", "fetched"))].inc_calls == [2]
    assert ingestion.children[(("collector", "rss"), ("status", "skipped"))].inc_calls == [0]
    assert api_calls.children[(("stage", "tier2"),)].inc_calls == [0]
    assert cost.children[(("stage", "tier2"),)].inc_calls == [0.0]
    assert failovers.children[(("stage", "unknown"),)].inc_calls == [None]
    assert degraded.children[(("stage", "tier2"),)].set_calls == [1]
    assert worker_errors.children[(("task_name", "sync_task"),)].inc_calls == [None]
    assert budget_denials.children[
        (("reason", "budget_exhausted"), ("tier", "tier2"))
    ].inc_calls == [None]
    assert drift_alerts.children[
        (("alert_type", "mean_brier_drift"), ("severity", "warning"))
    ].inc_calls == [None]
    assert reaper_resets.inc_calls == [0]
    assert source_stale.children[(("collector", "gdelt"),)].inc_calls == [0]
    assert catchup.children[(("collector", "rss"),)].inc_calls == [None]
    assert semantic_cache.children[(("result", "hit"), ("stage", "tier1"))].inc_calls == [None]
    assert backlog.set_calls == [0]
    assert dispatch.children[(("decision", "dispatched"), ("reason", "unspecified"))].inc_calls == [
        None
    ]
    assert dispatch.children[(("decision", "throttled"), ("reason", "quota"))].inc_calls == [None]
    assert ingested_language.children[(("language", "en"),)].inc_calls == [None]
    assert tier1_language.children[(("language", "bg"), ("outcome", "unknown"))].inc_calls == [None]
    assert tier2_language.children[(("language", "es"),)].inc_calls == [None]
    assert taxonomy.children[(("reason", "unknown"),)].inc_calls == [None]
    assert taxonomy_signal.children[
        (("signal_type", "unknown"), ("trend_id", "unknown"))
    ].inc_calls == [None]
    assert corroboration.children[(("mode", "unknown"), ("reason", "unspecified"))].inc_calls == [
        None
    ]
    assert suppressions.children[(("action", "unknown"), ("stage", "unknown"))].inc_calls == [None]
    assert embedding_inputs.children[(("entity_type", "trend"),)].inc_calls == [None]
    assert embedding_inputs.children[(("entity_type", "unknown"),)].inc_calls == [None]
    assert embedding_truncated.children[
        (("entity_type", "trend"), ("strategy", "truncate"))
    ].inc_calls == [None]
    assert embedding_dropped.children[
        (("entity_type", "trend"), ("strategy", "truncate"))
    ].inc_calls == [0]
    assert embedding_ratio.children[(("entity_type", "trend"),)].set_calls == [1.0]
    assert embedding_ratio.children[(("entity_type", "unknown"),)].set_calls == [0.0]
    assert retention_rows.children[
        (("action", "unknown"), ("mode", "dry_run"), ("table", "unknown"))
    ].inc_calls == [0]
    assert retention_runs.children[(("mode", "delete"), ("status", "unknown"))].inc_calls == [None]
