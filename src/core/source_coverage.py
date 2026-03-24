"""Coverage-health aggregation and persistence for recent source intake."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.coverage_models import CoverageSnapshot
from src.storage.models import ProcessingStatus, RawItem, Source

DEFAULT_COVERAGE_LOOKBACK_HOURS = 24
DEFAULT_COVERAGE_ARTIFACT_DIR = "artifacts/source_coverage"
MIN_DROP_ALERT_BASELINE = 5
WARN_DROP_RATIO = 0.5
CRITICAL_DROP_RATIO = 0.2
MAX_ALERTS = 20

_WORD_RE = re.compile(r"[a-z0-9]+")
_LANGUAGE_CODE_BY_NAME = {
    "arabic": "ar",
    "chinese": "zh",
    "english": "en",
    "french": "fr",
    "german": "de",
    "hebrew": "he",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
    "turkish": "tr",
    "ukrainian": "uk",
}


@dataclass(slots=True)
class CoverageCounts:
    """Coverage-state counters for one slice."""

    seen: int = 0
    processable: int = 0
    processed: int = 0
    deferred: int = 0
    skipped_by_language: int = 0
    pending_processable: int = 0
    processing: int = 0
    classified: int = 0
    noise: int = 0
    error: int = 0

    def apply(self, delta: CoverageCounts) -> None:
        self.seen += delta.seen
        self.processable += delta.processable
        self.processed += delta.processed
        self.deferred += delta.deferred
        self.skipped_by_language += delta.skipped_by_language
        self.pending_processable += delta.pending_processable
        self.processing += delta.processing
        self.classified += delta.classified
        self.noise += delta.noise
        self.error += delta.error


@dataclass(frozen=True, slots=True)
class CoverageSegment:
    """One row within a coverage dimension."""

    key: str
    label: str
    counts: CoverageCounts
    processed_ratio: float
    pending_ratio: float
    change_ratio: float | None


@dataclass(frozen=True, slots=True)
class CoverageDimensionSummary:
    """Coverage summary for a single dimension."""

    dimension: str
    multi_value: bool
    rows: tuple[CoverageSegment, ...]


@dataclass(frozen=True, slots=True)
class CoverageAlert:
    """Coverage drop alert derived from the previous snapshot."""

    severity: str
    dimension: str
    key: str
    label: str
    current_seen: int
    previous_seen: int
    change_ratio: float
    message: str


@dataclass(frozen=True, slots=True)
class CoverageHealthReport:
    """Recent intake coverage-health report."""

    generated_at: datetime
    window_start: datetime
    window_end: datetime
    lookback_hours: int
    total: CoverageCounts
    dimensions: tuple[CoverageDimensionSummary, ...]
    alerts: tuple[CoverageAlert, ...] = field(default_factory=tuple)
    snapshot_id: UUID | None = None
    artifact_path: str | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _slug_text(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    words = _WORD_RE.findall(normalized)
    if not words:
        return None
    return "-".join(words[:6])


def _normalize_language(value: str | None) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return "unknown"
    if normalized in _LANGUAGE_CODE_BY_NAME:
        return _LANGUAGE_CODE_BY_NAME[normalized]
    primary = normalized.split("-", 1)[0]
    if primary in _LANGUAGE_CODE_BY_NAME:
        return _LANGUAGE_CODE_BY_NAME[primary]
    if len(primary) >= 2:
        return primary[:2]
    return "unknown"


def _normalize_status(value: ProcessingStatus | str | None) -> str:
    if isinstance(value, ProcessingStatus):
        return value.value
    return _normalize_text(value) or ProcessingStatus.PENDING.value


def _normalize_topic_values(config: dict[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(config, dict):
        return ("unconfigured",)

    values: list[str] = []
    for key in ("categories", "themes"):
        raw = config.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item is not None)

    normalized = sorted({slug for item in values if (slug := _slug_text(item)) is not None})
    if not normalized:
        return ("unconfigured",)
    return tuple(normalized)


def _is_language_policy_marker(error_message: str | None, *, mode: str) -> bool:
    normalized = _normalize_text(error_message)
    return normalized.startswith("unsupported_language:") and normalized.endswith(f":{mode}")


def _counts_for_item(
    *,
    processing_status: ProcessingStatus | str | None,
    error_message: str | None,
) -> CoverageCounts:
    status = _normalize_status(processing_status)
    skipped_by_language = _is_language_policy_marker(error_message, mode="skip")
    deferred = _is_language_policy_marker(error_message, mode="defer")
    processable = not skipped_by_language and not deferred
    processed = processable and status in {
        ProcessingStatus.CLASSIFIED.value,
        ProcessingStatus.NOISE.value,
        ProcessingStatus.ERROR.value,
    }
    return CoverageCounts(
        seen=1,
        processable=int(processable),
        processed=int(processed),
        deferred=int(deferred),
        skipped_by_language=int(skipped_by_language),
        pending_processable=int(processable and status == ProcessingStatus.PENDING.value),
        processing=int(processable and status == ProcessingStatus.PROCESSING.value),
        classified=int(processable and status == ProcessingStatus.CLASSIFIED.value),
        noise=int(processable and status == ProcessingStatus.NOISE.value),
        error=int(processable and status == ProcessingStatus.ERROR.value),
    )


def _segment_from_counts(
    *,
    key: str,
    label: str,
    counts: CoverageCounts,
    previous_seen: int | None,
) -> CoverageSegment:
    processable = counts.processable
    processed_ratio = round(counts.processed / processable, 6) if processable else 0.0
    pending_ratio = round(counts.pending_processable / processable, 6) if processable else 0.0
    change_ratio = None
    if previous_seen is not None and previous_seen > 0:
        change_ratio = round(counts.seen / previous_seen, 6)
    return CoverageSegment(
        key=key,
        label=label,
        counts=counts,
        processed_ratio=processed_ratio,
        pending_ratio=pending_ratio,
        change_ratio=change_ratio,
    )


def _index_previous_seen(payload: dict[str, Any] | None) -> dict[tuple[str, str], int]:
    if not isinstance(payload, dict):
        return {}

    indexed: dict[tuple[str, str], int] = {}
    total = payload.get("total")
    if isinstance(total, dict):
        indexed[("total", "all")] = int(total.get("seen", 0) or 0)

    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list):
        return indexed

    for dimension_summary in dimensions:
        if not isinstance(dimension_summary, dict):
            continue
        dimension = _normalize_text(dimension_summary.get("dimension")) or "unknown"
        rows = dimension_summary.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _normalize_text(row.get("key")) or "unknown"
            counts = row.get("counts")
            if isinstance(counts, dict):
                indexed[(dimension, key)] = int(counts.get("seen", 0) or 0)
    return indexed


def _build_alerts(
    *,
    total: CoverageCounts,
    dimensions: tuple[CoverageDimensionSummary, ...],
    previous_payload: dict[str, Any] | None,
) -> tuple[CoverageAlert, ...]:
    previous_seen = _index_previous_seen(previous_payload)
    alerts: list[CoverageAlert] = []

    def maybe_add_alert(*, dimension: str, key: str, label: str, current_seen: int) -> None:
        previous = previous_seen.get((dimension, key))
        if previous is None or previous < MIN_DROP_ALERT_BASELINE:
            return
        ratio = current_seen / previous if previous else 0.0
        severity: str | None = None
        if current_seen == 0 or ratio <= CRITICAL_DROP_RATIO:
            severity = "critical"
        elif ratio <= WARN_DROP_RATIO:
            severity = "warning"
        if severity is None:
            return
        alerts.append(
            CoverageAlert(
                severity=severity,
                dimension=dimension,
                key=key,
                label=label,
                current_seen=current_seen,
                previous_seen=previous,
                change_ratio=round(ratio, 6),
                message=(
                    f"Recent coverage dropped for {dimension}={label} "
                    f"({current_seen} seen vs {previous} in the previous snapshot)."
                ),
            )
        )

    maybe_add_alert(dimension="total", key="all", label="all", current_seen=total.seen)
    for summary in dimensions:
        for row in summary.rows:
            maybe_add_alert(
                dimension=summary.dimension,
                key=row.key,
                label=row.label,
                current_seen=row.counts.seen,
            )

    alerts.sort(
        key=lambda row: (
            0 if row.severity == "critical" else 1,
            -(row.previous_seen - row.current_seen),
            row.dimension,
            row.key,
        )
    )
    return tuple(alerts[:MAX_ALERTS])


def _build_dimension_summary(
    *,
    dimension: str,
    multi_value: bool,
    counts_by_key: dict[str, CoverageCounts],
    previous_seen: dict[tuple[str, str], int],
) -> CoverageDimensionSummary:
    rows = [
        _segment_from_counts(
            key=key,
            label=key,
            counts=counts,
            previous_seen=previous_seen.get((dimension, key)),
        )
        for key, counts in counts_by_key.items()
    ]
    rows.sort(key=lambda row: (-row.counts.seen, row.key))
    return CoverageDimensionSummary(
        dimension=dimension,
        multi_value=multi_value,
        rows=tuple(rows),
    )


def serialize_coverage_report(report: CoverageHealthReport) -> dict[str, Any]:
    """Serialize a coverage report into JSON-friendly structures."""
    return cast("dict[str, Any]", _json_safe(asdict(report)))


def deserialize_coverage_report(payload: dict[str, Any]) -> CoverageHealthReport:
    """Deserialize a persisted payload into a coverage report."""

    def counts_from_mapping(mapping: dict[str, Any]) -> CoverageCounts:
        return CoverageCounts(
            seen=int(mapping.get("seen", 0) or 0),
            processable=int(mapping.get("processable", 0) or 0),
            processed=int(mapping.get("processed", 0) or 0),
            deferred=int(mapping.get("deferred", 0) or 0),
            skipped_by_language=int(mapping.get("skipped_by_language", 0) or 0),
            pending_processable=int(mapping.get("pending_processable", 0) or 0),
            processing=int(mapping.get("processing", 0) or 0),
            classified=int(mapping.get("classified", 0) or 0),
            noise=int(mapping.get("noise", 0) or 0),
            error=int(mapping.get("error", 0) or 0),
        )

    dimensions: list[CoverageDimensionSummary] = []
    for dimension_summary in payload.get("dimensions", []):
        if not isinstance(dimension_summary, dict):
            continue
        rows: list[CoverageSegment] = []
        for row in dimension_summary.get("rows", []):
            if not isinstance(row, dict):
                continue
            change_ratio_raw = row.get("change_ratio")
            change_ratio = None
            if isinstance(change_ratio_raw, int | float | str):
                change_ratio = float(change_ratio_raw)
            rows.append(
                CoverageSegment(
                    key=str(row.get("key", "unknown")),
                    label=str(row.get("label", "unknown")),
                    counts=counts_from_mapping(row.get("counts", {})),
                    processed_ratio=float(row.get("processed_ratio", 0.0) or 0.0),
                    pending_ratio=float(row.get("pending_ratio", 0.0) or 0.0),
                    change_ratio=change_ratio,
                )
            )
        dimensions.append(
            CoverageDimensionSummary(
                dimension=str(dimension_summary.get("dimension", "unknown")),
                multi_value=bool(dimension_summary.get("multi_value", False)),
                rows=tuple(rows),
            )
        )

    alerts: list[CoverageAlert] = []
    for alert in payload.get("alerts", []):
        if not isinstance(alert, dict):
            continue
        alerts.append(
            CoverageAlert(
                severity=str(alert.get("severity", "warning")),
                dimension=str(alert.get("dimension", "unknown")),
                key=str(alert.get("key", "unknown")),
                label=str(alert.get("label", "unknown")),
                current_seen=int(alert.get("current_seen", 0) or 0),
                previous_seen=int(alert.get("previous_seen", 0) or 0),
                change_ratio=float(alert.get("change_ratio", 0.0) or 0.0),
                message=str(alert.get("message", "")),
            )
        )

    snapshot_id = payload.get("snapshot_id")
    return CoverageHealthReport(
        generated_at=_as_utc(datetime.fromisoformat(str(payload["generated_at"]))),
        window_start=_as_utc(datetime.fromisoformat(str(payload["window_start"]))),
        window_end=_as_utc(datetime.fromisoformat(str(payload["window_end"]))),
        lookback_hours=int(payload.get("lookback_hours", DEFAULT_COVERAGE_LOOKBACK_HOURS)),
        total=counts_from_mapping(payload.get("total", {})),
        dimensions=tuple(dimensions),
        alerts=tuple(alerts),
        snapshot_id=UUID(str(snapshot_id)) if snapshot_id else None,
        artifact_path=str(payload["artifact_path"]) if payload.get("artifact_path") else None,
    )


async def build_source_coverage_report(
    session: AsyncSession,
    *,
    window_end: datetime | None = None,
    lookback_hours: int = DEFAULT_COVERAGE_LOOKBACK_HOURS,
    previous_snapshot_payload: dict[str, Any] | None = None,
) -> CoverageHealthReport:
    """Aggregate recent raw-item intake into coverage-health summaries."""
    effective_window_end = _as_utc(window_end or datetime.now(tz=UTC))
    effective_lookback_hours = max(1, int(lookback_hours))
    window_start = effective_window_end - timedelta(hours=effective_lookback_hours)

    rows = (
        await session.execute(
            select(
                RawItem.processing_status,
                RawItem.error_message,
                RawItem.language,
                Source.type,
                Source.source_tier,
                Source.config,
            )
            .join(Source, Source.id == RawItem.source_id)
            .where(RawItem.fetched_at >= window_start)
            .where(RawItem.fetched_at < effective_window_end)
        )
    ).all()

    total = CoverageCounts()
    accumulators: dict[str, dict[str, CoverageCounts]] = {
        "language": {},
        "source_family": {},
        "source_tier": {},
        "topic": {},
    }

    for processing_status, error_message, language, source_type, source_tier, config in rows:
        counts = _counts_for_item(
            processing_status=processing_status,
            error_message=error_message,
        )
        total.apply(counts)

        language_key = _normalize_language(language)
        family_key = str(getattr(source_type, "value", source_type) or "unknown")
        tier_key = _normalize_text(source_tier) or "unknown"
        topic_keys = _normalize_topic_values(config if isinstance(config, dict) else None)

        for dimension, key in (
            ("language", language_key),
            ("source_family", family_key),
            ("source_tier", tier_key),
        ):
            bucket = accumulators[dimension].setdefault(key, CoverageCounts())
            bucket.apply(counts)
        for topic_key in topic_keys:
            bucket = accumulators["topic"].setdefault(topic_key, CoverageCounts())
            bucket.apply(counts)

    previous_seen = _index_previous_seen(previous_snapshot_payload)
    dimensions: list[CoverageDimensionSummary] = []
    for dimension, multi_value in (
        ("language", False),
        ("source_family", False),
        ("source_tier", False),
        ("topic", True),
    ):
        dimensions.append(
            _build_dimension_summary(
                dimension=dimension,
                multi_value=multi_value,
                counts_by_key=accumulators[dimension],
                previous_seen=previous_seen,
            )
        )

    alerts = _build_alerts(
        total=total,
        dimensions=tuple(dimensions),
        previous_payload=previous_snapshot_payload,
    )
    return CoverageHealthReport(
        generated_at=effective_window_end,
        window_start=window_start,
        window_end=effective_window_end,
        lookback_hours=effective_lookback_hours,
        total=total,
        dimensions=tuple(dimensions),
        alerts=alerts,
    )


def write_source_coverage_artifact(
    report: CoverageHealthReport,
    *,
    artifact_dir: str | Path = DEFAULT_COVERAGE_ARTIFACT_DIR,
) -> Path:
    """Write the report payload to a timestamped JSON artifact and stable alias."""
    output_dir = Path(artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = serialize_coverage_report(report)
    json_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    timestamp = report.generated_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"source-coverage-{timestamp}.json"
    latest_path = output_dir / "source-coverage-latest.json"

    output_path.write_text(json_text, encoding="utf-8")
    latest_path.write_text(json_text, encoding="utf-8")
    return output_path


async def load_latest_coverage_snapshot(session: AsyncSession) -> CoverageSnapshot | None:
    """Return the most recent persisted coverage snapshot, if present."""
    return cast(
        "CoverageSnapshot | None",
        await session.scalar(
            select(CoverageSnapshot).order_by(CoverageSnapshot.generated_at.desc()).limit(1)
        ),
    )


async def persist_coverage_snapshot(
    session: AsyncSession,
    *,
    report: CoverageHealthReport,
    artifact_path: str | None,
) -> CoverageSnapshot:
    """Persist a coverage report as a snapshot row."""
    snapshot = CoverageSnapshot(
        generated_at=report.generated_at,
        window_start=report.window_start,
        window_end=report.window_end,
        lookback_hours=report.lookback_hours,
        artifact_path=artifact_path,
        payload={},
    )
    session.add(snapshot)
    await session.flush()
    snapshot.payload = serialize_coverage_report(
        CoverageHealthReport(
            generated_at=report.generated_at,
            window_start=report.window_start,
            window_end=report.window_end,
            lookback_hours=report.lookback_hours,
            total=report.total,
            dimensions=report.dimensions,
            alerts=report.alerts,
            snapshot_id=snapshot.id,
            artifact_path=artifact_path,
        )
    )
    return snapshot
