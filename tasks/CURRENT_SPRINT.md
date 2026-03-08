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
- Newly queued from 2026-03-07 prompt/model evaluation follow-up intake:
- Newly queued from 2026-03-07 workflow/coverage hardening intake
  (sequencing required; one task per branch/PR):
  - `TASK-251` Normalize Task Specs Around Explicit Input/Output Contracts
  - `TASK-252` Add a Canonical Post-Task Local Gate Without Overloading `make agent-check`
  - `TASK-254` Refine and Unify Agent-Facing Context Entry Points
  - `TASK-255` Add a Targeted Docstring Quality Gate for High-Value Surfaces
  - `TASK-256` Enforce the Task Completion Contract for Tests, Docs, and Gate Re-Runs
  - `TASK-257` Fail Pre-Commit and CI When Coverage Drops Below 100%
- Newly queued from 2026-03-08 workflow-centralization hardening follow-up intake
  (remaining recommended sequencing: `TASK-259` → `TASK-261` → `TASK-263` →
  `TASK-264` → `TASK-262` → `TASK-265` → `TASK-266`; one task per branch/PR):
  - `TASK-259` Add a Mechanical Done-State Verifier and Explicit Lifecycle States
  - `TASK-261` Auto-Handle Docker Readiness for Workflow Gates
  - `TASK-262` Enforce No Early Completion Claims in Agent Workflow Guidance
  - `TASK-263` Route Repo Workflow Automation Through Horadus CLI and Skill
  - `TASK-264` Enforce Horadus CLI, Skill, and Docs Drift Consistency
  - `TASK-265` Add Structured Horadus CLI Friction Logging
  - `TASK-266` Add Daily Horadus Friction Summary Automation
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
- `TASK-240` Keep `docs-freshness` from dropping dev dependencies ✅
- `TASK-242` Unblock Gold-Set Benchmark and Capture Quality Blockers ✅
  completion note: restored runnable benchmark preflight, generated candidate eval artifacts, did not promote a new baseline because quality remained unacceptable, and queued the follow-up fixes into the active sprint backlog.
- `TASK-243` Stabilize Tier-1 Routing Quality Under Eval and Runtime Load ✅
  completion note: changed runtime Tier-1 safe default to single-item requests, kept benchmark batch mode as explicit diagnostic mode with artifact metadata, and recorded paired realtime vs batch evidence showing batch still underperforms realtime.
- `TASK-244` Persist Per-Item Benchmark Failure Diagnostics ✅
  completion note: benchmark artifacts now persist per-item Tier-1/Tier-2 outcomes, failure category/message, best-effort raw model output, and compact success summaries for faster debugging.
- `TASK-245` Add Explicit Tier-1 Scoring Rubric and Calibration Examples ✅
  completion note: added explicit Tier-1 score bands and targeted fiction/documentary/commentary examples, added prompt regression tests, and ran a fresh gold-set benchmark before promotion.
- `TASK-246` Enrich Tier-2 Signal Payload Beyond Keyword Bags ✅
  completion note: Tier-2 payloads now include human-readable indicator descriptions plus specificity/abstention prompt guidance and regression tests, but the 10-item human-verified benchmark showed no measurable accuracy improvement so no baseline was promoted.
- `TASK-247` Evaluate GPT-5 Reasoning Models for Tier-1/Tier-2 ✅
  completion note: benchmarked cache-disabled GPT-5 candidate configs on the shared 10-item human-verified slice, found `gpt-5-nano` + `minimal` best for Tier-1 and `gpt-5-mini` + `low` best for Tier-2, and documented that Responses API migration is not required for the switch because Chat Completions already supports the needed structured-output and reasoning controls.
- `TASK-248` Evaluate `gpt-5-nano` with Minimal Reasoning for Tier-1 ✅
  completion note: reused the cache-disabled `TASK-247` artifact to close the Tier-1-specific decision; `gpt-5-nano` with `minimal` reasoning beat both `gpt-4.1-nano` and `gpt-5-nano` `low` on the shared human-verified slice, so it is the recommended Tier-1 target after runtime reasoning controls land.
- `TASK-249` Add First-Class Reasoning-Effort Controls for LLM Routes ✅
  completion note: promoted `reasoning_effort` to a first-class Tier-1/Tier-2 runtime and benchmark route setting, omitted unsupported reasoning/temperature params safely in the shared adapter, and surfaced active reasoning metadata in benchmark artifacts plus Tier-2 degraded-mode telemetry.
- `TASK-250` Make Eval Artifacts Strictly Reproducible and Traceable ✅
  completion note: benchmark and audit artifacts now record source-control provenance, prompt/config fingerprints, dataset fingerprints, and normalized invocation metadata, while the docs keep `ai/eval/results/*.json` ignored and route all committed eval artifacts through `ai/eval/baselines/`.
- `TASK-241` Fix Horadus CLI Global Flag Precedence ✅
- `TASK-215` Gate task completion on current-head PR review comments ✅
- `TASK-239` External architecture review backlog intake preservation (2026-03-06) ✅
- `TASK-253` Raise Measured Runtime Coverage to 100% with Behavior-Focused Tests ✅
  completion note: the repo now reaches `100%` measured coverage for `src/`
  in the unit coverage run (`1294 passed`) using behavior-focused tests across
  CLI, API, workers, ingestion, eval, and processing/runtime edge cases rather
  than new omit rules or snapshot padding.
- `TASK-258` Add a Canonical Horadus Task Completion Command ✅
  completion note: `horadus tasks finish` now owns the task-completion lifecycle
  end to end, `make task-finish` delegates to the CLI as a thin compatibility
  wrapper, and the legacy shell entrypoint is reduced to a compatibility shim
  rather than a second lifecycle engine.
- `TASK-260` Add a Full Local CI-Parity Gate in Horadus CLI ✅
  completion note: `horadus tasks local-gate --full` now owns the canonical
  post-task CI-parity validation path, `make local-gate` delegates to the CLI
  as a thin compatibility wrapper, and the command list now covers tracked
  artifacts, docs freshness, repo-wide lint/type/unit/security checks,
  integration, and build verification in one backpressure-friendly sequence.
