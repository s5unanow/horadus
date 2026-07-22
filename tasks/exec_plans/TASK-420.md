# TASK-420: Add SSRF guard and resource caps to collector HTTP fetch path

## Status

- Owner: Codex
- Started: 2026-07-22
- Current state: Verified; ledger closure and delivery in progress
- Planning Gates: Required — P0 security work crosses shared ingestion, worker, configuration, documentation, and test surfaces and materially touches allowlisted Python hotspots.

## Goal (1-3 lines)

Make every RSS and GDELT HTTP fetch fail closed for non-public destinations,
including redirect and DNS-rebinding paths, while bounding response memory,
redirect count, timeouts, and connection-pool use.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-420`), `INTAKE-0070`
- Runtime/code touchpoints: `src/ingestion/rss_collector.py`, `src/ingestion/gdelt_client.py`, `src/workers/_task_collectors.py`, `src/core/config.py`
- Preconditions/dependencies: HTTPX 0.28.1 request streaming and `sni_hostname` request extension; all configured production RSS/GDELT endpoints are public Internet sources.

## Outputs

- Expected behavior/artifacts: a single-owner safe-fetch module; public-IP pinning with original Host/SNI preservation; bounded manual redirects; bounded streamed bodies; explicit worker client limits/timeouts; environment documentation and no-network regressions.
- Validation evidence: focused safe-fetch/collector/worker unit tests, `make agent-check`, Docker integration proof, canonical full local gate, PR review, and strict lifecycle verification.

## Non-Goals

- Explicitly excluded work: Telegram transport changes; GDELT query semantics; URL dedup normalization; proxy support for collector egress; an internal-destination allowlist; changes to extraction or persistence behavior beyond fetch failures.

## Scope

- In scope: RSS feed and article fetches, GDELT API fetches, redirect handling, DNS/IP policy, response byte caps, client construction, settings/docs, and regression tests.
- Out of scope: application API clients, LLM clients, webhooks, report fetching, and network calls in tests.

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: resolve every destination, require every answer to be globally routable, connect to one validated numeric IP, preserve the original hostname through `Host` and TLS `sni_hostname`, disable automatic redirects, re-run the same validation for each bounded redirect, and stream into a byte-limited buffer.
- Rejected simpler alternative: hostname pre-validation followed by a normal HTTPX request still permits a second DNS lookup and rebinding; automatic redirects also skip hop-by-hop policy checks.
- First integration proof: run the existing Docker integration suite after focused no-network unit tests, before the canonical full gate.
- Hotspot Outcome: reduce — keep the new policy in a single-owner module, shrink the allowlisted collector modules through delegation, and consolidate adjacent collector settings so `src/core/config.py` also drops below its prior ratchet rather than expanding any allowlist.
- Waivers: none.

## Plan (Keep Updated)

1. Confirm active-task context, enumerate fetch callers, pin HTTPX/runtime constraints, and start the guarded task branch.
2. Add the safe-fetch module with URL validation, asynchronous resolution, public-IP pinning, redirect revalidation, bounded streaming, and a bounded client factory.
3. Route RSS and GDELT callers through the helper; add settings and operator docs without growing allowlisted hotspot maxima.
4. Add no-network helper, collector, and worker regressions, including an unaffected public-fetch path.
5. Run focused tests, code-health/code-shape checks, Docker integration, local review if recommended, and the full local gate.
6. Close ledgers, commit, finish through PR review/merge, and verify strict lifecycle on synced `main`.

## Decisions (Timestamped)

- 2026-07-22: Reject proxy-based collector egress in this slice; worker clients use `trust_env=False` so IP pinning cannot be bypassed by ambient proxy settings.
- 2026-07-22: Reject internal-network overrides initially; public-source ingestion should fail closed, and an override would weaken the core SSRF invariant.
- 2026-07-22: Preserve existing retry ownership in each collector; the shared helper performs one bounded request chain and surfaces typed HTTP/status/safety failures.
- 2026-07-22: Reject multicast explicitly in addition to `is_global` because Python's IP address model reports multicast ranges as global; focused regressions cover every blocked address class named by the task.
- 2026-07-22: Send `Connection: close` and disable HTTP/2 for collector clients so a connection pinned for one hostname cannot be pooled for a different hostname that resolves to the same address.
- 2026-07-22: Local review found that DNS lookup failures lost the collectors' established transient retry path and that source-specific timeouts overrode the new global read cap. Resolution failures now surface as `httpx.ConnectError`, and each request uses the lower of its source timeout and the configured global ceiling.
- 2026-07-22: Fresh-head review found decompression, multi-address availability, and DNS-timeout gaps. Collector requests now require identity encoding before streaming, try every validated public address in resolver order on network failure, and bound DNS resolution with the configured connect timeout.
- 2026-07-22: The first canonical full gate exposed committed-diff code-health growth that dirty-worktree checks could not see. HTTP settings and client construction were extracted into single-owner modules, synthetic integration URLs now use public IP literals, and existing config, collector, worker, and integration-test files are flat or smaller against `main`.

## Risks / Foot-guns

- DNS answers containing both public and non-public addresses -> reject the whole resolution result rather than choosing the public subset.
- HTTPS certificate/SNI breakage after numeric-IP pinning -> retain the original hostname in `Host` and HTTPX/httpcore `sni_hostname`.
- Redirect loops or downgrade abuse -> bound hop count and revalidate scheme/host/IP on every Location target.
- Mock-heavy tests accidentally bypassing the real pinning contract -> exercise the helper through `httpx.MockTransport` and assert the numeric request host plus original SNI/Host metadata.
- Hotspot ratchet growth -> keep policy and buffering in the new module and run code-health before the full gate.

## Validation Commands

- `uv run --no-sync pytest tests/unit/ingestion tests/unit/workers/test_tasks_additional.py -q`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus eval code-health --output-dir ai/eval/results`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`
- `uv run --no-sync horadus tasks finish TASK-420`
- `uv run --no-sync horadus tasks lifecycle TASK-420 --strict`

## Notes / Links

- Spec: backlog task plus this execution plan.
- Relevant modules: `src/ingestion/rss_collector.py`, `src/ingestion/gdelt_client.py`, `src/workers/_task_collectors.py`, `src/core/config.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
- 2026-07-22 validation: 135 focused unit tests passed; `make agent-check` passed (ruff, mypy, code shape, docstring policy, code health, and full unit suites); `make test-integration-docker` passed 20 tests after its synthetic host fixtures were routed through a deterministic public-address resolver.
- 2026-07-22 live smoke: a real fetch of `https://example.com/` through `SafeHTTPFetcher` returned HTTP 200 while connecting to the validated numeric address with the original Host/SNI. No automated test performs network I/O.
- Pre-commit `horadus tasks local-review --format json` reported no branch diff because the review target is `main...HEAD`; rerun after the implementation commit and before push.
- Post-commit local review completed through the configured Codex fallback after Claude timed out. Both P2 findings were accepted and fixed: DNS lookup failures retain transient network retry semantics, and the environment read timeout is a hard ceiling over source-specific values.
- Fresh-head local review reported three more findings, all accepted and fixed: encoded bodies are rejected before iteration, all validated public addresses receive ordered network fallback, and DNS resolution is covered by the connect timeout. The expanded focused suite passes 138 tests with clean mypy and code-shape checks.
- The canonical full gate then passed through code health and all 2,869 unit tests but identified four uncovered safe-fetch lines/branches. JSON decoding and all-address failure now have direct regressions, and unreachable loop guards were removed by expressing the redirect loop around its non-empty pinned-address invariant.
- Final canonical `horadus tasks local-gate --full` passed all 17 stages: artifact/docs checks, code shape, docstrings, zero-regression code health, formatting/lint, mypy, taxonomy/eval validation, 100% unit coverage, secret scan, Bandit, dependency and lockfile audits, Docker integration, and package build.
