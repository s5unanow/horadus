# Daily Agentic Assessment Report

Date: 2026-02-19
Repo: Horadus (geopolitical intelligence backend)
Goal: Make the project more agentic-oriented and easier for agents to work on (max 3 improvements)

## Current State (Quick Read)

This repo is already unusually “agent-friendly” for a hobby backend:
- Strong workflow guardrails in `AGENTS.md` and `Makefile` (one-task branches, preflight, human-gated steps).
- Deterministic scoring + evidence lineage (excellent for auditability and replayability).
- Cost/budget guardrails and explicit retention policies (prevents runaway agent behavior).

The main gap is that agent *execution* is not yet a first-class product surface: context assembly, run-level traceability, and evaluation loops are still mostly “operator discipline” rather than enforced primitives.

## 1) Add an Agent Task Context Pack (Deterministic Brief Generator)

**Justification**
- Most agent failures in mature codebases come from missing constraints (task scope, “don’t touch X”, human-gated steps, source-of-truth hierarchy).
- You already encode the rules; the missing piece is a deterministic “single bundle” that every agent run can consume (and that can be attached to a run ledger later).
- This reduces onboarding time and makes “agent handoff” reliable (new agent can pick up with the same context payload).

**Step-by-step integration plan**
1. Implement `scripts/agent_context.py`:
   - Input: `TASK-XXX` plus optional `--include` flags.
   - Output: one Markdown doc that embeds: `AGENTS.md`, `tasks/CURRENT_SPRINT.md`, `tasks/specs/<task>.md` (when present), and a short file index derived from `rg` matches (e.g., top 10 relevant paths in `src/`).
2. Add `make agent-context TASK=XXX`:
   - Writes to `assessments/agent_context/TASK-XXX-context.md`.
   - Fails fast if the task is not in `tasks/BACKLOG.md` (prevents “ghost tasks”).
3. Add `docs/AGENT_RUNBOOK.md`:
   - Defines “minimum context required” for any agent execution.
   - Documents how `[REQUIRES_HUMAN]` tasks are represented in the context pack (explicit stop points).
4. Add a small unit test in `tests/` validating:
   - Required sections exist in the output.
   - The output is stable (ordering deterministic).
5. Optional (nice-to-have): teach `make task-start` to optionally emit the context pack when starting a task branch.

## 2) Introduce an Agent Run Ledger (Runs + Actions + Approvals + Cost Summary)

**Justification**
- You have good observability for pipeline behavior, but not a unified *agent run* record that answers: “what did the agent do, with what prompts/tools, under what budget, and who approved what?”
- A run ledger is the backbone for governance, replay, and debugging. It also enables “human-in-the-loop” controls to be enforced as data, not just docs.
- This aligns with your existing auditability goals (evidence lineage, deterministic scoring) and extends them to the agent layer.

**Step-by-step integration plan**
1. Add Alembic migration with two tables:
   - `agent_runs`: `id`, `run_kind` (e.g., `tier1`, `tier2`, `reporting`, `ops`), `task_id` (string like `TASK-XXX`), `started_at`, `ended_at`, `status`, `model_provider`, `model_name`, `prompt_version`, `budget_policy`, `estimated_cost_usd`, `metadata` (JSON).
   - `agent_actions`: `id`, `run_id`, `action_kind` (e.g., `llm_call`, `db_write`, `external_fetch`, `tool_exec`), `input_sha256`, `output_sha256`, `status`, `requires_human_approval`, `approved_by`, `approved_at`, `metadata` (JSON).
2. Add SQLAlchemy models + a thin recorder service (e.g., `src/core/agent_ledger.py`) used by:
   - Tier-1 filter invocation
   - Tier-2 classifier invocation
   - Report generation invocation
   This should be “side-effect only” (recording) and not change scoring behavior.
3. Add an explicit “approval-required boundary” pattern:
   - For any action flagged `requires_human_approval=true`, code must fail closed unless `approved_at` exists.
   - Start with `run_kind=ops` actions (e.g., retention cleanup with destructive mode) to validate the pattern.
4. Add API endpoints to query runs/actions for debugging:
   - `GET /api/v1/agent-runs`
   - `GET /api/v1/agent-runs/{id}`
   - `PATCH /api/v1/agent-actions/{id}` for approvals (admin-key protected).
5. Integrate retention:
   - Extend the existing retention cleanup worker to prune `agent_*` tables by age (and optionally keep “runs with approvals” longer).
6. Add fixture-backed tests ensuring:
   - Ledger rows are created on mocked LLM calls.
   - Approval-required actions block without approval.

## 3) Build a No-Network Agent Regression Harness (Replay + Evals)

**Justification**
- Agentic systems need “tight eval loops” or they drift. Without a replay/eval harness, prompt tweaks and pipeline refactors regress silently.
- Your deterministic scoring model is ideal for evals: LLM outputs can be recorded/mocked, and score deltas can be asserted exactly.
- A harness that runs without network calls fits your testing guardrails and enables CI gating.

**Step-by-step integration plan**
1. Add fixture directory `ai/evals/agent/`:
   - `raw_items.jsonl` (minimal normalized inputs)
   - `tier1_expected.json` (expected relevance decisions)
   - `tier2_expected.json` (expected structured signals)
   - `score_expected.json` (expected delta_log_odds per trend/signal)
2. Add a “mock LLM provider” mode:
   - Environment toggle (e.g., `LLM_MODE=mock`).
   - Implementation returns fixture outputs keyed by deterministic hashes of inputs.
3. Implement `scripts/run_agent_eval.py`:
   - Runs the pipeline over fixtures with `LLM_MODE=mock`.
   - Outputs a concise diff report and non-zero exit on mismatch.
4. Add `make agent-eval` and wire into CI as a required job (fast, offline).
5. Add `docs/AGENT_EVALS.md`:
   - How to add fixtures
   - Versioning rules for prompts (tie `prompt_version` to eval fixtures)
   - How to handle intentional behavior changes (update fixtures + explain)

## Adoption Notes

- These improvements are intentionally “backend-shaped”: they don’t require new infrastructure, but they make agent work reproducible, governable, and easy to debug.
- Recommended implementation order: (1) Context Pack → (3) Eval Harness → (2) Run Ledger.
