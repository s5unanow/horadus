"""
Export helpers for calibration dashboard snapshots.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

if TYPE_CHECKING:
    from src.core.calibration_dashboard import CalibrationDashboardReport


@dataclass(frozen=True)
class DashboardExportResult:
    """Paths written by dashboard export."""

    json_path: Path
    html_path: Path
    latest_json_path: Path
    latest_html_path: Path
    index_html_path: Path


def build_calibration_dashboard_payload(
    report: CalibrationDashboardReport,
    *,
    trend_limit: int | None = None,
) -> dict[str, Any]:
    """
    Build a JSON-serializable dashboard payload.

    `trend_limit` restricts exported trend movement rows for lighter static artifacts.
    """
    payload = cast("dict[str, Any]", _json_safe(asdict(report)))
    if trend_limit is not None:
        payload["trend_movements"] = payload.get("trend_movements", [])[: max(1, trend_limit)]
    return payload


def export_calibration_dashboard(
    report: CalibrationDashboardReport,
    *,
    output_dir: str | Path = "artifacts/dashboard",
    trend_limit: int | None = None,
) -> DashboardExportResult:
    """
    Export dashboard payload as JSON + static HTML.

    Writes timestamped artifacts and updates stable latest/index aliases.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    payload = build_calibration_dashboard_payload(report, trend_limit=trend_limit)
    html = render_calibration_dashboard_html(payload)
    json_text = json.dumps(payload, indent=2, sort_keys=True)

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_path / f"calibration-dashboard-{timestamp}.json"
    html_path = output_path / f"calibration-dashboard-{timestamp}.html"
    latest_json_path = output_path / "calibration-dashboard-latest.json"
    latest_html_path = output_path / "calibration-dashboard-latest.html"
    index_html_path = output_path / "index.html"

    json_path.write_text(json_text + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    latest_json_path.write_text(json_text + "\n", encoding="utf-8")
    latest_html_path.write_text(html, encoding="utf-8")
    index_html_path.write_text(html, encoding="utf-8")

    return DashboardExportResult(
        json_path=json_path,
        html_path=html_path,
        latest_json_path=latest_json_path,
        latest_html_path=latest_html_path,
        index_html_path=index_html_path,
    )


def render_calibration_dashboard_html(payload: dict[str, Any]) -> str:
    """Render a lightweight standalone HTML dashboard."""
    generated_at = escape(str(payload.get("generated_at", "")))
    total_predictions = int(payload.get("total_predictions", 0))
    resolved_predictions = int(payload.get("resolved_predictions", 0))
    mean_brier = payload.get("mean_brier_score")
    mean_brier_text = "n/a" if mean_brier is None else f"{float(mean_brier):.3f}"

    alerts = payload.get("drift_alerts", [])
    alert_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(str(row.get('severity', '')))}</td>"
            f"<td>{escape(str(row.get('alert_type', '')))}</td>"
            f"<td>{escape(str(row.get('metric_name', '')))}</td>"
            f"<td>{escape(str(row.get('metric_value', '')))}</td>"
            f"<td>{escape(str(row.get('threshold', '')))}</td>"
            f"<td>{escape(str(row.get('sample_size', '')))}</td>"
            f"<td>{escape(str(row.get('message', '')))}</td>"
            "</tr>"
        )
        for row in alerts
        if isinstance(row, dict)
    )
    if not alert_rows:
        alert_rows = "<tr><td colspan='7'>No active drift alerts.</td></tr>"

    trend_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(str(row.get('trend_name', '')))}</td>"
            f"<td>{float(row.get('current_probability', 0.0)):.1%}</td>"
            f"<td>{float(row.get('weekly_change', 0.0)):+.1%}</td>"
            f"<td>{escape(str(row.get('risk_level', '')))}</td>"
            f"<td>{escape(', '.join(row.get('top_movers_7d', [])))}</td>"
            f"<td><code>{escape(str(row.get('movement_chart', '')))}</code></td>"
            "</tr>"
        )
        for row in payload.get("trend_movements", [])
        if isinstance(row, dict)
    )
    if not trend_rows:
        trend_rows = "<tr><td colspan='6'>No trend movement rows available.</td></tr>"

    curve_rows = "".join(
        (
            "<tr>"
            f"<td>{float(row.get('bucket_start', 0.0)):.0%}-{float(row.get('bucket_end', 0.0)):.0%}</td>"
            f"<td>{int(row.get('prediction_count', 0))}</td>"
            f"<td>{float(row.get('expected_rate', 0.0)):.1%}</td>"
            f"<td>{float(row.get('actual_rate', 0.0)):.1%}</td>"
            f"<td>{float(row.get('calibration_error', 0.0)):.3f}</td>"
            "</tr>"
        )
        for row in payload.get("calibration_curve", [])
        if isinstance(row, dict)
    )
    if not curve_rows:
        curve_rows = "<tr><td colspan='5'>No calibration data available.</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Horadus Calibration Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --line: #cbd5e1;
      --accent: #0ea5e9;
    }}
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; margin: 0; background: var(--bg); color: var(--text); }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
    h1 {{ margin: 0 0 8px; }}
    p.meta {{ margin: 0 0 20px; color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .label {{ font-size: 12px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.04em; }}
    .value {{ font-size: 20px; margin-top: 6px; font-weight: 600; }}
    section {{ margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #f1f5f9; }}
    tr:last-child td {{ border-bottom: 0; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 12px; background: #e2e8f0; color: #0f172a; }}
    .critical {{ background: #fee2e2; color: #991b1b; }}
    .warning {{ background: #fef3c7; color: #92400e; }}
    a {{ color: var(--accent); text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <h1>Calibration Dashboard</h1>
    <p class="meta">Generated at {generated_at}</p>
    <div class="grid">
      <div class="card"><div class="label">Mean Brier</div><div class="value">{mean_brier_text}</div></div>
      <div class="card"><div class="label">Resolved Predictions</div><div class="value">{resolved_predictions}</div></div>
      <div class="card"><div class="label">Total Predictions</div><div class="value">{total_predictions}</div></div>
      <div class="card"><div class="label">Raw JSON</div><div class="value"><a href="calibration-dashboard-latest.json">download</a></div></div>
    </div>

    <section>
      <h2>Drift Alerts</h2>
      <table>
        <thead>
          <tr><th>Severity</th><th>Type</th><th>Metric</th><th>Value</th><th>Threshold</th><th>Samples</th><th>Message</th></tr>
        </thead>
        <tbody>{alert_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Trend Movement</h2>
      <table>
        <thead>
          <tr><th>Trend</th><th>Probability</th><th>Weekly Change</th><th>Risk</th><th>Top Movers</th><th>Chart</th></tr>
        </thead>
        <tbody>{trend_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Calibration Curve</h2>
      <table>
        <thead>
          <tr><th>Bucket</th><th>Count</th><th>Expected</th><th>Actual</th><th>Error</th></tr>
        </thead>
        <tbody>{curve_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value
