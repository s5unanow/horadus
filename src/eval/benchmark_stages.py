"""Execution-stage helpers for gold-set benchmark runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from src.processing.llm_policy import apply_latest_active_route_metadata


async def run_tier1_benchmark_stage(
    *,
    tier1: Any | None,
    tier1_recorder: Any,
    tier1_batch_size: int,
    gold_items: list[Any],
    raw_items: list[Any],
    trends: list[Any],
    tier1_metrics: Any,
    tier1_usage: Any,
    item_results_by_id: dict[str, dict[str, Any]],
    item_uuid: Callable[[str], UUID],
    extract_stage_raw_output: Callable[..., str | None],
    serialize_tier1_prediction: Callable[[Any], dict[str, Any]],
    stage_failure: Callable[..., dict[str, Any]],
    stage_success: Callable[..., dict[str, Any]],
) -> None:
    if tier1 is None:
        return

    for batch_start in range(0, len(gold_items), tier1_batch_size):
        item_batch = gold_items[batch_start : batch_start + tier1_batch_size]
        raw_batch = raw_items[batch_start : batch_start + tier1_batch_size]
        tier1_recorder.reset()
        try:
            tier1_results, tier1_call_usage = await tier1.classify_items(raw_batch, trends)
        except ValueError as exc:
            raw_output = extract_stage_raw_output(recorder=tier1_recorder, subject=tier1)
            for item in item_batch:
                tier1_metrics.record_failure(gold=item)
                item_results_by_id[item.item_id]["tier1"] = stage_failure(
                    error_category=type(exc).__name__,
                    error_message=str(exc),
                    raw_model_output=raw_output,
                )
            continue

        tier1_usage.prompt_tokens += tier1_call_usage.prompt_tokens
        tier1_usage.completion_tokens += tier1_call_usage.completion_tokens
        tier1_usage.api_calls += tier1_call_usage.api_calls
        tier1_usage.estimated_cost_usd += tier1_call_usage.estimated_cost_usd
        apply_latest_active_route_metadata(target_usage=tier1_usage, source_usage=tier1_call_usage)
        tier1_usage.used_secondary_route = (
            tier1_usage.used_secondary_route or tier1_call_usage.used_secondary_route
        )

        predictions_by_item = {result.item_id: result for result in tier1_results}
        for item in item_batch:
            prediction = predictions_by_item.get(item_uuid(item.item_id))
            if prediction is None:
                tier1_metrics.record_failure(gold=item)
                item_results_by_id[item.item_id]["tier1"] = stage_failure(
                    error_category="MissingPrediction",
                    error_message="Tier 1 benchmark received no prediction for input item",
                    raw_model_output=extract_stage_raw_output(
                        recorder=tier1_recorder,
                        subject=tier1,
                    ),
                )
                continue

            tier1_metrics.record(gold=item, predicted=prediction)
            item_results_by_id[item.item_id]["tier1"] = stage_success(
                predicted=serialize_tier1_prediction(prediction),
                raw_model_output=extract_stage_raw_output(
                    recorder=tier1_recorder,
                    subject=tier1,
                ),
            )


async def run_tier2_benchmark_stage(
    *,
    tier2: Any,
    tier2_recorder: Any,
    gold_items: list[Any],
    trends: list[Any],
    tier2_metrics: Any,
    tier2_usage: Any,
    item_results_by_id: dict[str, dict[str, Any]],
    build_event: Callable[[Any], Any],
    extract_first_impact: Callable[[Any], Any | None],
    extract_stage_raw_output: Callable[..., str | None],
    serialize_tier2_prediction: Callable[[Any], dict[str, Any]],
    tier2_failure_stage: Callable[..., str],
    stage_failure: Callable[..., dict[str, Any]],
    stage_success: Callable[..., dict[str, Any]],
) -> None:
    for item in gold_items:
        if item.tier2 is None:
            continue

        event = build_event(item)
        tier2_recorder.reset()
        try:
            _, tier2_call_usage = await tier2.classify_event(
                event=event,
                trends=trends,
                context_chunks=[f"{item.title}\n\n{item.content}"],
            )
        except ValueError as exc:
            error_category = type(exc).__name__
            error_message = str(exc)
            tier2_metrics.record(
                expected=item.tier2,
                predicted=None,
                failure_stage=tier2_failure_stage(
                    error_category=error_category,
                    error_message=error_message,
                ),
            )
            item_results_by_id[item.item_id]["tier2"] = stage_failure(
                error_category=error_category,
                error_message=error_message,
                raw_model_output=extract_stage_raw_output(recorder=tier2_recorder, subject=tier2),
            )
            continue

        tier2_usage.prompt_tokens += tier2_call_usage.prompt_tokens
        tier2_usage.completion_tokens += tier2_call_usage.completion_tokens
        tier2_usage.api_calls += tier2_call_usage.api_calls
        tier2_usage.estimated_cost_usd += tier2_call_usage.estimated_cost_usd
        apply_latest_active_route_metadata(target_usage=tier2_usage, source_usage=tier2_call_usage)
        tier2_usage.used_secondary_route = (
            tier2_usage.used_secondary_route or tier2_call_usage.used_secondary_route
        )

        tier2_prediction = extract_first_impact(event)
        tier2_metrics.record(
            expected=item.tier2,
            predicted=tier2_prediction,
            failure_stage=(
                tier2_failure_stage(
                    error_category="MissingPrediction",
                    error_message="Tier 2 benchmark received no trend impact prediction",
                )
                if tier2_prediction is None
                else None
            ),
        )
        if tier2_prediction is None:
            item_results_by_id[item.item_id]["tier2"] = stage_failure(
                error_category="MissingPrediction",
                error_message="Tier 2 benchmark received no trend impact prediction",
                raw_model_output=extract_stage_raw_output(recorder=tier2_recorder, subject=tier2),
            )
        else:
            item_results_by_id[item.item_id]["tier2"] = stage_success(
                predicted=serialize_tier2_prediction(tier2_prediction),
                raw_model_output=extract_stage_raw_output(recorder=tier2_recorder, subject=tier2),
            )
