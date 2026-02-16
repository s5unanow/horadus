# OpenTelemetry Tracing

**Last Verified**: 2026-02-16

This runbook enables end-to-end tracing across API requests, Celery workers,
SQLAlchemy, Redis, and outbound HTTP/LLM calls.

## Scope

With tracing enabled, Horadus emits spans for:

- FastAPI request lifecycle
- Celery task execution
- SQLAlchemy database operations
- Redis client operations
- HTTP clients (including OpenAI-compatible LLM calls)

Celery publish/consume trace context is propagated via task headers so worker
spans join the originating request trace.

## Configuration

Set the following environment values:

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=horadus-backend
OTEL_SERVICE_NAMESPACE=horadus
OTEL_TRACES_SAMPLER_RATIO=1.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

Optional auth/tenant headers:

```bash
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <token>,x-tenant=<tenant-id>
```

## Local Quickstart (Collector + UI)

Run Jaeger all-in-one with OTLP receivers and trace UI:

```bash
docker run --rm -it \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  jaegertracing/all-in-one:1.57
```

Then start Horadus API and worker with tracing env enabled, execute a request
that queues a worker task, and inspect traces at:

- <http://localhost:16686>

## Validation Checklist

1. Confirm API spans appear under `OTEL_SERVICE_NAME`.
2. Trigger a workflow that enqueues Celery work.
3. Verify worker spans share the same trace ID as the originating API request.
4. Confirm child spans include DB (`sqlalchemy`), Redis, and HTTP client calls.
5. If spans are missing, validate endpoint/headers and `OTEL_ENABLED=true`.
