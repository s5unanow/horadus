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
- `TASK-251` Normalize Task Specs Around Explicit Input/Output Contracts
- `TASK-252` Add a Canonical Post-Task Local Gate Without Overloading `make agent-check`
- `TASK-254` Refine and Unify Agent-Facing Context Entry Points
- `TASK-255` Add a Targeted Docstring Quality Gate for High-Value Surfaces
- `TASK-256` Enforce the Task Completion Contract for Tests, Docs, and Gate Re-Runs
- `TASK-272` Keep Active Reasoning Metadata Consistent Across Mixed-Route Runs
- `TASK-274` Standardize Task PR Titles on `TASK-XXX: ...`
- `TASK-288` Convert RFC-001 Context Retrieval Plan Into Approved Implementation Queue `[REQUIRES_HUMAN]` — human review/approval pending before follow-up tasks are finalized
- `TASK-080` Telegram Collector Task Wiring `[REQUIRES_HUMAN]` — manual execution/approval pending (carried from Sprint 3 close)
- `TASK-189` Restrict `/health` and `/metrics` exposure outside development `[REQUIRES_HUMAN]`
- `TASK-190` Harden admin-key compare + API key store file permissions `[REQUIRES_HUMAN]`

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
