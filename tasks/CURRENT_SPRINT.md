# Current Sprint

**Sprint Goal**: Reset live planning surfaces, keep archive access explicit, and carry unfinished hardening work into a compact Sprint 4 queue.
**Sprint Number**: 4  
**Sprint Dates**: 2026-03-10 to 2026-03-24
**Source-of-truth policy**: See `AGENTS.md` → `Canonical Source-of-Truth Hierarchy`

---

## Active Tasks

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
- `TASK-255` Add a Targeted Docstring Quality Gate for High-Value Surfaces
- `TASK-256` Enforce the Task Completion Contract for Tests, Docs, and Gate Re-Runs
- `TASK-272` Keep Active Reasoning Metadata Consistent Across Mixed-Route Runs
- `TASK-288` Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue `[REQUIRES_HUMAN]` — human review/approval pending before follow-up tasks are finalized
- `TASK-080` Telegram Collector Task Wiring `[REQUIRES_HUMAN]` — manual execution/approval pending (carried from Sprint 3 close)
- `TASK-189` Restrict `/health` and `/metrics` exposure outside development `[REQUIRES_HUMAN]`
- `TASK-190` Harden admin-key compare + API key store file permissions `[REQUIRES_HUMAN]`

## Descoped This Sprint

- `TASK-254` Refine and Unify Agent-Facing Context Entry Points — descoped after `TASK-329`; keep `README.md`, `docs/AGENT_RUNBOOK.md`, and `context-pack` as the default navigation layer
- `TASK-267` Add a Thin Repo Workflow Skill Routed to AGENTS and Horadus — descoped after `TASK-329`; keep using the runbook plus `ops/skills/horadus-cli/` unless a concrete gap emerges later

## Human Blocker Metadata

- TASK-080 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-189 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-190 | owner=human-operator | last_touched=2026-03-03 | next_action=2026-03-05 | escalate_after_days=7
- TASK-288 | owner=human-operator | last_touched=2026-03-09 | next_action=2026-03-10 | escalate_after_days=7

## Telegram Launch Scope

- launch_scope: excluded_until_task_080_done
- decision_date: 2026-03-03
- rationale: Telegram ingestion remains explicitly out of launch scope until the human-gated wiring/sign-off task closes.

## Completed This Sprint

- `TASK-292` Right-Size Live Task Ledgers and Archive Historical Planning Surfaces ✅
- `TASK-294` Preserve Closed Task Bodies in Quarterly Archive Shards ✅
- `TASK-295` Enforce Pre-Merge Task Closure State ✅
- `TASK-293` Decouple CLI Tests from Live Task IDs ✅
- `TASK-296` Let Guarded Task Start Handle Task-Ledger Intake Safely ✅
- `TASK-297` Split `task_commands.py` Into Focused Workflow Modules ✅
- `TASK-300` Introduce a Versioned CLI Shell and Move Legacy CLI to `v1` ✅
- `TASK-302` Isolate Horadus CLI Tests Into a Self-Contained Suite ✅
- `TASK-299` Build an Isolated `v2` Task Workflow and Cut Over from `tasks-v2` ✅
- `TASK-301` Move All Horadus CLI Functionality to `v2` and Delete `v1` ✅
- `TASK-298` Add Phase -1 Planning Gates Without Heavy Process Overhead ✅
- `TASK-303` Extract Repo Workflow Into a Dedicated Tooling Home ✅
- `TASK-304` Realign Agent Workflow Docs and Remove Policy Duplication ✅
- `TASK-305` Let Guarded Task Start Carry Target Planning Intake Files ✅
- `TASK-306` Unblock Canonical Finish When Only Outdated Review Threads Remain ✅
- `TASK-307` Make `horadus tasks finish` Behave Like a Stateful Review Loop ✅
- `TASK-308` Keep Workflow Guidance Thin Outside `AGENTS.md` ✅
- `TASK-309` Refresh `horadus tasks finish` Immediately After a New PR Head Is Pushed ✅
- `TASK-310` Remove Duplicated App Runtime Modules from `src/horadus_cli/v2/runtime` ✅
- `TASK-311` Move Horadus CLI Into the Tooling Home and Isolate It from App Runtime Imports ✅
- `TASK-312` Split `tests/horadus_cli/v2/test_cli.py` into Focused Ownership-Aligned Modules ✅
- `TASK-313` Split `task_workflow_core.py` Into Focused Workflow Modules ✅
- `TASK-314` Split Finish Workflow Into an Independent Package ✅
- `TASK-315` Split `docs_freshness.py` Into Focused Workflow Modules ✅
- `TASK-316` Decompose `_docs_freshness_checks.py` Into Focused Internal Modules ✅
- `TASK-317` Decompose `review.py` Into Focused Internal Modules ✅
- `TASK-318` Decompose `validate_assessment_artifacts.py` Into Focused Internal Modules ✅
- `TASK-319` Decompose `ops_commands.py` Into Focused Internal Modules ✅
- `TASK-320` Tighten `ops_commands.py` Internal Seams After the Initial Split ✅
- `TASK-321` Remove obsolete `src/core` workflow shims ✅
- `TASK-322` Harden `horadus tasks finish` Review Request Dedupe and Feedback Detection ✅
- `TASK-323` Collapse repetitive finish refresh test scaffolding ✅
- `TASK-324` Decompose `task_workflow_preflight.py` Into Focused Internal Modules ✅
- `TASK-325` Decompose `src/workers/tasks.py` Into Focused Internal Modules ✅
- `TASK-326` Let `horadus tasks finish` Bootstrap Missing PRs Canonically ✅
- `TASK-327` Preserve current-head PR-summary thumbs-up across `finish` reruns ✅
- `TASK-328` Add Code-Shape Guardrails to Prevent Module Sprawl ✅
- `TASK-329` Right-Size `AGENTS.md` Around Policy Invariants and Thin Helper Surfaces ✅
- `TASK-251` Normalize Task Specs Around Explicit Input/Output Contracts ✅
- `TASK-252` Add a Canonical Post-Task Local Gate Without Overloading `make agent-check` ✅
- `TASK-274` Standardize Task PR Titles on `TASK-XXX: ...` ✅
- `TASK-330` Trim stale backlog items and archive already-landed workflow tasks ✅
