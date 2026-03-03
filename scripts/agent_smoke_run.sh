#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "${repo_root}"

host="${AGENT_SMOKE_HOST:-127.0.0.1}"
port="${AGENT_SMOKE_PORT:-18000}"
base_url="http://${host}:${port}"
max_retries="${AGENT_SMOKE_HEALTH_RETRIES:-30}"
retry_delay="${AGENT_SMOKE_HEALTH_DELAY_SECONDS:-1}"

log_dir="artifacts/agent"
mkdir -p "${log_dir}"
server_log="${log_dir}/$(date -u +%Y%m%dT%H%M%SZ)-agent-smoke-server.log"

cleanup() {
  if [[ -n "${server_pid:-}" ]] && kill -0 "${server_pid}" >/dev/null 2>&1; then
    kill "${server_pid}" >/dev/null 2>&1 || true
    wait "${server_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[agent] starting uvicorn on ${base_url}"
RUNTIME_PROFILE=agent \
ENVIRONMENT=development \
API_HOST="${host}" \
API_PORT="${port}" \
uv run --no-sync uvicorn src.api.main:app --host "${host}" --port "${port}" \
  >"${server_log}" 2>&1 &
server_pid=$!

echo "[agent] waiting for /health"
ready=0
for _ in $(seq 1 "${max_retries}"); do
  if curl --silent --show-error --max-time 1 "${base_url}/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep "${retry_delay}"
done

if [[ "${ready}" -ne 1 ]]; then
  echo "[agent] health check failed: ${base_url}/health did not become ready"
  echo "[agent] server log: ${server_log}"
  exit 2
fi

echo "[agent] running smoke checks"
if [[ -n "${AGENT_SMOKE_API_KEY:-}" ]]; then
  uv run --no-sync horadus agent smoke --base-url "${base_url}" --api-key "${AGENT_SMOKE_API_KEY}"
else
  uv run --no-sync horadus agent smoke --base-url "${base_url}"
fi
smoke_status=$?

echo "[agent] smoke exit code: ${smoke_status}"
echo "[agent] server log: ${server_log}"
exit "${smoke_status}"
