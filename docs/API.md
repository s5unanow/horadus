# API Reference

This service exposes REST endpoints under `/api/v1` plus health probes.

Interactive documentation:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

## Authentication

All endpoints document `X-API-Key` in OpenAPI for forward compatibility.

- Header: `X-API-Key: <key>`
- Current behavior: optional (not enforced yet)
- Planned enforcement: TASK-025

Example:

```bash
curl -H "X-API-Key: dev-key" http://localhost:8000/api/v1/trends
```

## Health

- `GET /health`
- `GET /health/live`
- `GET /health/ready`

Example:

```bash
curl http://localhost:8000/health
```

## Sources

- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `GET /api/v1/sources/{source_id}`
- `PATCH /api/v1/sources/{source_id}`
- `DELETE /api/v1/sources/{source_id}`

Create example:

```bash
curl -X POST http://localhost:8000/api/v1/sources \
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

## Trends

- `GET /api/v1/trends`
- `POST /api/v1/trends`
- `POST /api/v1/trends/sync-config`
- `GET /api/v1/trends/{trend_id}`
- `PATCH /api/v1/trends/{trend_id}`
- `DELETE /api/v1/trends/{trend_id}`
- `GET /api/v1/trends/{trend_id}/evidence`
- `GET /api/v1/trends/{trend_id}/history`
- `GET /api/v1/trends/{trend_id}/retrospective`

Retrospective example:

```bash
curl "http://localhost:8000/api/v1/trends/<trend-id>/retrospective?start_date=2026-01-01T00:00:00Z&end_date=2026-02-01T00:00:00Z"
```

## Events

- `GET /api/v1/events`
- `GET /api/v1/events/{event_id}`

Note: event query endpoints are currently scaffolded and return `501` until implemented.

## Reports

- `GET /api/v1/reports`
- `GET /api/v1/reports/{report_id}`
- `GET /api/v1/reports/latest/weekly`
- `GET /api/v1/reports/latest/monthly`

List monthly reports:

```bash
curl "http://localhost:8000/api/v1/reports?report_type=monthly&limit=10"
```
