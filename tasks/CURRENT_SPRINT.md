# Current Sprint

**Sprint Goal**: TBD (planning)
**Sprint Number**: 3  
**Sprint Dates**: 2026-03-04 to 2026-03-18
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

- TASKs pulled in: all backlog tasks not listed in `tasks/COMPLETED.md`.
- Newly queued from 2026-03-06 external architecture review intake
  (sequencing required; implementation must remain one task per branch/PR):
  - `TASK-227` Make Corroboration Provenance-Aware Instead of Source-Count-Aware
  - `TASK-228` Harden Trend Forecast Contracts with Explicit Horizon and Resolution Semantics
  - `TASK-229` Add a Novelty Lane Outside the Active Trend List
  - `TASK-230` Add Coverage Observability Beyond Source Freshness
  - `TASK-231` Extend Event Invalidation into a Compensating Restatement Ledger
  - `TASK-232` Strengthen Operator Adjudication Workflow for High-Risk Events
  - `TASK-233` Support Multi-Horizon Trend Variants for the Same Underlying Theme
  - `TASK-234` Make Uncertainty and Momentum First-Class Trend State
  - `TASK-235` Add Event Split/Merge Lineage for Evolving Stories
  - `TASK-236` Add Canonical Entity Registry for Actors, Organizations, and Locations
  - `TASK-237` Add Dynamic Reliability Diagnostics and Time-Varying Source Credibility
  - `TASK-238` Prioritize Tier-2 Budget with Value-of-Information Scheduling

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
- `TASK-210` Unify assessment artifact contract across writers and validator ✅
- `TASK-211` Add 7-day novelty gate with `All clear` fallback for assessment roles ✅
- `TASK-212` Ground assessment task references against current sprint truth ✅
- `TASK-213` Suppress cross-role overlap before assessment artifacts are written ✅
- `TASK-214` Switch PO/BA automations to change-triggered publishing under fully human-gated queues ✅
- `TASK-216` Agent-Facing Horadus CLI Initiative ✅
- `TASK-217` Refactor CLI into an internal package ✅
- `TASK-218` Add task and sprint workflow commands to `horadus` ✅
- `TASK-219` Add structured triage input collection command ✅
- `TASK-220` Migrate wrapper targets and agent docs to the CLI ✅
- `TASK-221` Add repo-owned Horadus CLI skill ✅
- `TASK-222` Dogfood Horadus CLI triage flow and capture follow-ups ✅
- `TASK-223` Add status filters and compact output to `horadus tasks search` ✅
- `TASK-224` Surface human-blocker urgency in task and triage outputs ✅
- `TASK-215` Gate task completion on current-head PR review comments ✅
- `TASK-239` External architecture review backlog intake preservation (2026-03-06) ✅
