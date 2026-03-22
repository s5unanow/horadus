# API Reference

This service exposes REST endpoints under `/api/v1` plus health probes.

Interactive documentation:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

## Authentication

API key auth and rate limiting are controlled by environment config.

- Header: `X-API-Key: <key>`
- Admin header for key management: `X-Admin-API-Key: <admin-key>`
- Set `API_AUTH_ENABLED=true` to enforce auth globally
- Configure keys via `API_KEY` and/or `API_KEYS`
- Privileged mutation/control routes require a configured `X-Admin-API-Key` in addition to a valid `X-API-Key`; authenticated non-admin API keys are not an admin fallback
- Privileged routes include API key management, source create/update/delete, trend create/update/delete/sync/outcome recording, and feedback/override/taxonomy-gap mutation endpoints
- Per-key default rate limit is controlled by `API_RATE_LIMIT_PER_MINUTE`
- Rate-limit algorithm is configured via `API_RATE_LIMIT_STRATEGY` (`fixed_window` default, `sliding_window` optional)
- On throttling, API returns `429` with `Retry-After` seconds

## Privileged Write Contract

The current operator/admin write contract is enforced for API key management
and the privileged trend/feedback mutation routes documented below.

Headers:
- `X-Idempotency-Key: <opaque-key>` is required on every covered privileged write
- `If-Match: <revision_token>` is additionally required on revision-sensitive writes

Semantics:
- reusing the same idempotency key for a prior successful or in-flight write returns `409`
- reusing an idempotency key with a different request intent also returns `409`
- missing `If-Match` on a revision-sensitive write returns `428`
- stale revision tokens return `412`
- durable privileged-write audit rows capture actor metadata, target, request intent, outcome, revision basis, and resulting linkage ids where applicable

Current route matrix:
- Idempotency only: `POST /api/v1/auth/keys`, `POST /api/v1/auth/keys/{key_id}/rotate`, `DELETE /api/v1/auth/keys/{key_id}`, `POST /api/v1/trends`, `POST /api/v1/trends/sync-config`, `POST /api/v1/trends/{trend_id}/outcomes`
- Idempotency + revision token: `PATCH /api/v1/trends/{trend_id}`, `DELETE /api/v1/trends/{trend_id}`, `PATCH /api/v1/taxonomy-gaps/{gap_id}`, `POST /api/v1/events/{event_id}/feedback`, `POST /api/v1/trends/{trend_id}/override`

Revision tokens are surfaced on the resource payloads used for read-before-write
flows:
- `TrendResponse.revision_token`
- `EventResponse.revision_token` and `EventDetailResponse.revision_token`
- `TaxonomyGapResponse.revision_token`
- `FeedbackResponse.target_revision_token` for writes that mutate an event or trend

Example:

```bash
curl -H "X-API-Key: dev-key" http://localhost:8000/api/v1/trends
```

## Health

- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /metrics` (Prometheus exposition format)

Readiness semantics:
- `/health/ready` returns `200` only when critical dependencies are healthy.
- If dependencies are unavailable, it returns `503` with a `not_ready` payload.

Example:

```bash
curl http://localhost:8000/health
```

## Sources

- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `GET /api/v1/sources/freshness`
- `GET /api/v1/sources/{source_id}`
- `PATCH /api/v1/sources/{source_id}`
- `DELETE /api/v1/sources/{source_id}`

Create example:

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "X-API-Key: dev-key" \
  -H "X-Admin-API-Key: admin-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "rss",
    "name": "Reuters World",
    "url": "https://feeds.reuters.com/Reuters/worldNews",
    "credibility_score": 0.95,
    "source_tier": "wire",
    "reporting_type": "secondary",
    "config": {"check_interval_minutes": 30},
    "is_active": true
  }'
```

Freshness status example:

```bash
curl "http://localhost:8000/api/v1/sources/freshness"
```

Freshness response includes:
- stale summary (`stale_count`, `stale_collectors`)
- bounded catch-up plan (`catchup_dispatch_budget`, `catchup_candidates`)
- per-source freshness rows (`age_seconds`, `stale_after_seconds`, `is_stale`)

## Trends

- `GET /api/v1/trends`
- `POST /api/v1/trends`
- `POST /api/v1/trends/sync-config`
- `GET /api/v1/trends/{trend_id}`
- `GET /api/v1/trends/{trend_id}/definition-history`
- `PATCH /api/v1/trends/{trend_id}`
- `DELETE /api/v1/trends/{trend_id}`
- `GET /api/v1/trends/{trend_id}/evidence`
- `GET /api/v1/trends/{trend_id}/history`
- `GET /api/v1/trends/{trend_id}/retrospective`
- `POST /api/v1/trends/{trend_id}/simulate`
- `POST /api/v1/trends/{trend_id}/outcomes`
- `GET /api/v1/trends/{trend_id}/calibration`

Privileged trend mutations require both `X-API-Key` and `X-Admin-API-Key`.
Config sync is only available through `POST /api/v1/trends/sync-config`.
`GET /api/v1/trends?sync_from_config=true` is rejected with `400`.
`POST /api/v1/trends/sync-config` accepts only repo-owned directories under
`config/trends` (the default root or a descendant); traversal, symlink escape,
and arbitrary server-local paths are rejected with `400`.

Trend responses now include:
- `risk_level` (`low`/`guarded`/`elevated`/`high`/`severe`)
- `probability_band` (lower/upper bound)
- `confidence` (`low`/`medium`/`high`)
- `top_movers_7d` (highest-impact recent evidence summaries)
- `forecast_contract` (explicit question, structured horizon, resolver source/basis, and closure semantics)
- `revision_token` (optimistic-concurrency token for privileged writes)

Trend config sync and `POST /api/v1/trends` now require an explicit
`forecast_contract`. `PATCH /api/v1/trends/{trend_id}` may omit the field only
when the stored trend definition already has one and the caller is not changing
the forecast contract.
Backfill existing YAML definitions in `config/trends/` by adding the contract
block in place while preserving each trend's existing `id`; do not rotate trend
IDs during this migration because `runtime_trend_id` must continue to match
`definition.id`.

Retrospective example:

```bash
curl "http://localhost:8000/api/v1/trends/<trend-id>/retrospective?start_date=2026-01-01T00:00:00Z&end_date=2026-02-01T00:00:00Z"
```

Retrospective responses include narrative grounding metadata:
- `grounding_status` (`grounded`, `fallback`, `flagged`)
- `grounding_violation_count`
- optional `grounding_references.unsupported_claims`

Counterfactual simulation example (non-persistent):

```bash
curl -X POST "http://localhost:8000/api/v1/trends/<trend-id>/simulate" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "inject_hypothetical_signal",
    "signal_type": "military_movement",
    "indicator_weight": 0.04,
    "source_credibility": 0.9,
    "corroboration_count": 3,
    "novelty_score": 1.0,
    "direction": "escalatory",
    "severity": 0.8,
    "confidence": 0.95
  }'
```

Record an outcome for calibration:

```bash
curl -X POST "http://localhost:8000/api/v1/trends/<trend-id>/outcomes" \
  -H "X-API-Key: dev-key" \
  -H "X-Admin-API-Key: admin-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "outcome": "occurred",
    "outcome_date": "2026-02-07T00:00:00Z",
    "outcome_notes": "Confirmed by multiple independent sources",
    "recorded_by": "analyst@horadus"
  }'
```

Fetch trend calibration report:

```bash
curl "http://localhost:8000/api/v1/trends/<trend-id>/calibration"
```

## Events

- `GET /api/v1/events`
- `GET /api/v1/events/{event_id}`

Feedback mutations are exposed under:
- `PATCH /api/v1/taxonomy-gaps/{gap_id}`
- `POST /api/v1/events/{event_id}/feedback`
- `POST /api/v1/trends/{trend_id}/override`

These routes require both `X-API-Key` and `X-Admin-API-Key`.
`PATCH /api/v1/taxonomy-gaps/{gap_id}`, `POST /api/v1/events/{event_id}/feedback`,
and `POST /api/v1/trends/{trend_id}/override` also require:
- `X-Idempotency-Key`
- `If-Match` with the latest `revision_token` for the target taxonomy gap/event/trend

Feedback write responses now include `target_revision_token` so the caller can
chain subsequent writes against the new resource revision.

Supported event filters:
- `category` (string)
- `trend_id` (UUID)
- `lifecycle` (`emerging`, `confirmed`, `fading`, `archived`)
- `contradicted` (`true`/`false`)
- `days` (1..30), `limit` (1..200)

## Reports

- `GET /api/v1/reports`
- `GET /api/v1/reports/{report_id}`
- `GET /api/v1/reports/latest/weekly`
- `GET /api/v1/reports/latest/monthly`
- `GET /api/v1/reports/calibration`

List monthly reports:

```bash
curl "http://localhost:8000/api/v1/reports?report_type=monthly&limit=10"
```

Calibration dashboard example:

```bash
curl "http://localhost:8000/api/v1/reports/calibration"
```

Calibration dashboard responses include `drift_alerts` when Brier/bucket error
thresholds are breached after minimum sample requirements are met.
Responses also include `coverage` guardrail metrics (resolved ratio and per-trend
low-sample breakdown) for calibration SLO monitoring.
Responses now also include advisory-only `source_reliability` and
`source_tier_reliability` diagnostics with sample-size confidence gating
(`eligible` / `confidence`) to prevent over-interpreting sparse outcome samples.
When `CALIBRATION_DRIFT_WEBHOOK_URL` is configured, alert payloads are also sent
to the webhook with bounded retry/backoff on transient delivery failures.
Operational response guidance for these alerts is documented in
`docs/CALIBRATION_RUNBOOK.md`.

Report `statistics` for weekly/monthly entries now include `contradiction_analytics`
with resolved/unresolved counts, resolution rate, and action mix for contradicted events.
Report narrative generation supports a pilot Responses API mode via
`LLM_REPORT_API_MODE=responses`; migration details and rollback are documented in
`docs/RESPONSES_API_MIGRATION.md`.
Report responses now also include narrative grounding metadata:
- `grounding_status` (`grounded`, `fallback`, `flagged`)
- `grounding_violation_count`
- optional `grounding_references.unsupported_claims`

## Budget

- `GET /api/v1/budget`

Returns current UTC-day LLM usage by tier (`tier1`, `tier2`, `embedding`) with
call counters, token totals, estimated cost, and remaining daily budget.
Tier-1 and Tier-2 processing calls support automatic primary/secondary model
failover on transient provider errors (429/5xx/timeouts) when secondary models
are configured. Each route now performs bounded retry/backoff before switching
or surfacing terminal failure.
Tier-1 and Tier-2 request strict JSON-schema constrained outputs by default;
when a model/provider returns a 400 schema-unsupported response, Horadus falls
back to `json_object` mode for compatibility while retaining Pydantic
validation.

Example:

```bash
curl "http://localhost:8000/api/v1/budget"
```

## Auth

- `GET /api/v1/auth/keys`
- `POST /api/v1/auth/keys`
- `DELETE /api/v1/auth/keys/{key_id}`
- `POST /api/v1/auth/keys/{key_id}/rotate`

Privileged auth writes require:
- `X-API-Key`
- `X-Admin-API-Key`
- `X-Idempotency-Key`
- `DELETE /api/v1/auth/keys/{key_id}`
- `POST /api/v1/auth/keys/{key_id}/rotate`

Create key example:

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: $API_ADMIN_KEY" \
  -d '{"name":"analytics-dashboard","rate_limit_per_minute":90}'
```

## Feedback

- `GET /api/v1/feedback`
- `GET /api/v1/review-queue`
- `GET /api/v1/taxonomy-gaps`
- `POST /api/v1/events/{event_id}/feedback` (`pin`, `mark_noise`, `invalidate`)
- `POST /api/v1/trends/{trend_id}/override`
- `PATCH /api/v1/taxonomy-gaps/{gap_id}` (`open`, `resolved`, `rejected`)

Invalidate example:

```bash
curl -X POST "http://localhost:8000/api/v1/events/<event-id>/feedback" \
  -H "Content-Type: application/json" \
  -d '{"action":"invalidate","notes":"Analyst invalidation after contradiction review"}'
```

Review queue example:

```bash
curl "http://localhost:8000/api/v1/review-queue?days=7&limit=25&unreviewed_only=true"
```

Taxonomy gaps example:

```bash
curl "http://localhost:8000/api/v1/taxonomy-gaps?days=7&status=open"
```
