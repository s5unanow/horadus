# Current Sprint

**Sprint Goal**: TBD (planning)
**Sprint Number**: 3  
**Sprint Dates**: 2026-03-04 to 2026-03-18
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- TASKs pulled in: all backlog tasks not listed in `tasks/COMPLETED.md`.

- `TASK-080` Telegram Collector Task Wiring `[REQUIRES_HUMAN]` — manual execution/approval pending (postponed at Sprint 2 close)
- `TASK-189` Restrict `/health` and `/metrics` exposure outside development `[REQUIRES_HUMAN]`
- `TASK-190` Harden admin-key compare + API key store file permissions `[REQUIRES_HUMAN]`

## Human Blocker Metadata

- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-190 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7

## Telegram Launch Scope

- launch_scope: excluded_until_task_080_done
- decision_date: 2026-03-03
- rationale: Telegram ingestion remains explicitly out of launch scope until the human-gated wiring/sign-off task closes.

---

## Completed This Sprint

- `TASK-164` Add one-shot agent smoke run target (serve → smoke → exit) ✅
- `TASK-165` Make `horadus agent smoke` robust across auth/environment settings ✅
- `TASK-166` Add fast agent gate target (`make agent-check`) ✅
- `TASK-167` Add context-efficient backpressure wrappers for noisy commands ✅
- `TASK-168` Add `horadus doctor` (or `make doctor`) self-diagnostic command ✅
- `TASK-169` Add offline fixtures and a dry-run pipeline path (no network, no LLM) ✅
- `TASK-170` Enforce “no network in tests” mechanically ✅
- `TASK-171` Align Claude Code permissions policy with repo workflow ✅
- `TASK-172` Add short “agent runbook index” doc (canonical commands) ✅
- `TASK-173` Add “task context pack” helper (`scripts/task_context_pack.sh`) ✅
- `TASK-184` Human-gated blocker aging SLA + explicit Telegram scope decision ✅
- `TASK-185` PROJECT_STATUS freshness SLA tied to sprint deltas ✅
- `TASK-186` Assessment date-integrity guard (filename vs content) ✅
- `TASK-187` Agent task-eligibility preflight (prevent policy-violating starts) ✅
- `TASK-188` Cross-role promotion de-duplication guard (assessment proposals) ✅
- `TASK-191` Cross-stage SLO/error-budget release gate ✅
- `TASK-192` Cluster drift sentinel (scheduled quality monitor) ✅
- `TASK-196` Branch-policy hardening guardrails for autonomous execution ✅
- `TASK-193` Degraded-mode policy for sustained LLM failover ✅
- `TASK-197` Enforce local integration test gate before push/PR ✅
- `TASK-198` External review backlog intake preservation (2026-03-05) ✅
