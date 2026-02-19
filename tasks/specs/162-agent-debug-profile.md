# TASK-162: Agent debugging runtime profile (low-noise, fail-fast, single-request)

## Summary

Add a dedicated runtime profile optimized for agentic self-check/debugging
flows (Codex / Claude Code):

- fewer/noisy logs by default (reduce context pollution)
- failures are loud (optionally fail-fast)
- deterministic “serve → curl → exit” runs (exit after N requests)

This must be **independent** of `ENVIRONMENT` to avoid conflating “deployment
environment” with “debug execution profile”.

## Goals

- Provide a safe and ergonomic way for an agent to run short-lived smoke checks
  against a live server process.
- Reduce operator/agent cognitive load (predictable output, minimal logs).
- Keep production safety intact (agent profile must not weaken prod deployments).

## Non-goals

- Implementing user login/roles (Horadus uses API keys, not user accounts).
- Replacing CI checks; this is a local/ops convenience layer.

## Proposed Interface

### Environment variables

One of:

- `RUNTIME_PROFILE=agent` (preferred: explicit enum), or
- `AGENT_MODE=true` (boolean)

Agent profile knobs:

- `AGENT_EXIT_AFTER_REQUESTS` (int, default `1`)
- `AGENT_SHUTDOWN_ON_ERROR` (bool, default `true`)
- `AGENT_DEFAULT_LOG_LEVEL` (optional override; otherwise set a conservative
  default like `WARNING`)

### Safety guardrails

Hard protections (fail-fast on invalid use):

- Refuse agent profile when `ENVIRONMENT=production`.
- Prefer requiring loopback bind in agent profile (e.g., `API_HOST` must be
  `127.0.0.1` or `localhost`), or require an explicit override like
  `AGENT_ALLOW_NON_LOOPBACK=true`.

### Behavior changes in agent profile

- Minimal logging (lower log level by default; optionally suppress uvicorn
  access logs).
- Middleware that counts requests and triggers a graceful shutdown after N.
- Error hook/exception handler that triggers shutdown (and process non-zero) on
  unhandled exceptions when `AGENT_SHUTDOWN_ON_ERROR=true`.

### CLI helper

Add `horadus agent smoke` (name can vary) that:

- hits a small set of endpoints via HTTP (e.g., `/health`, `/openapi.json`,
  `/api/v1/trends` if auth is enabled and a key is available)
- prints concise pass/fail lines
- exits non-zero on any failure

This command should not require external network calls; it should target the
locally running server.

## Notes on Auth

The upstream idea mentions “disable login completely”. For Horadus, that maps
to API key auth:

- The safest default is **not** to disable auth automatically.
- If “auth off” is supported for agent profile, it must be guarded (dev-only,
  loopback-only) to prevent accidental exposure.
- Alternatively, provide an “agent key” bootstrap convenience for local smoke
  checks (documented in the CLI helper output).

## Acceptance Criteria (Detailed)

- Agent profile can be enabled via a single explicit knob, independent of
  `ENVIRONMENT`.
- Agent profile supports exit-after-N and shutdown-on-error behavior.
- Agent profile defaults to low-noise logging.
- CLI helper exists and is deterministic (simple output, non-zero on failure).
- Guardrails prevent agent profile use in production.
- Tests cover the middleware/shutdown logic and guardrails (no external network
  calls).

## Test Plan

- Unit test the request-counter shutdown middleware using FastAPI’s test client.
- Unit test “refuse in production” settings validation.
- Ensure tests do not spin up a real network listener.
