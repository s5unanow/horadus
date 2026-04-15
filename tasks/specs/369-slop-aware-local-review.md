# TASK-369: Make Local Pre-Push Review Slop-Aware for Changed Files

## Problem Statement

`horadus tasks local-review` currently gives providers the branch diff and a
generic review contract, but it does not explicitly steer them toward the
repo's code-health failure modes for changed files. That leaves the advisory
pre-push review path weaker than the surrounding deterministic gates for
hotspot expansion, concern sprawl, and verbosity or duplication growth.

The repo already computes changed-file code-health artifacts in the local gate.
This task should reuse that existing structural signal in the local-review
prompt so providers receive a sharper review target without inventing a second
diff-analysis flow or changing the repo-owned output contract.

## Inputs

- Workflow policy in `AGENTS.md`
- Backlog contract for `TASK-369`
- Operator guidance in `docs/AGENT_RUNBOOK.md`
- Shared workflow surfaces:
  - `tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py`
  - `tools/horadus/python/horadus_workflow/task_workflow_local_review.py`
  - `tools/horadus/python/horadus_workflow/code_health.py`
- Existing unit coverage in `tests/horadus_cli/v2/test_task_local_review.py`

## Outputs

- Local-review prompts that explicitly ask for hotspot expansion,
  multi-concern growth, and verbosity or duplication regressions alongside
  ordinary bug-risk findings
- Prompt context that includes a bounded summary of changed-file code-health
  findings when the artifact is available
- Regression tests that cover prompt rendering, artifact reuse, and unaffected
  provider-adapter behavior
- Runbook guidance that documents the stronger local-review prompt contract

## Non-Goals

- Changing the marker-line output contract or findings-first result shape
- Adding a second code-health analyzer or new artifact format
- Changing remote PR review or finish-gate semantics

**Planning Gates**: Required — shared workflow review guidance and provider-facing prompt behavior are changing.

## Phase -1 / Pre-Implementation Gates (Only If `Planning Gates: Required`)

- `Simplicity Gate`: Extend the existing local-review context and prompt
  renderers instead of adding a new review orchestration layer or separate
  changed-file analysis command.
- `Anti-Abstraction Gate`: Reuse the existing code-health artifact format and
  local-review provider adapters; a new wrapper around review context assembly
  is not justified for a single prompt-contract change.
- `Integration-First Gate`:
  - Validation target: `tests/horadus_cli/v2/test_task_local_review.py`,
    `tests/workflow/`, and the canonical local/integration gates.
  - Exercises: prompt rendering with and without code-health artifacts,
    unchanged provider command selection, and operator-visible runbook guidance.
- `Code Shape Gate`: Not applicable — no allowlisted oversized Python hotspot
  is expected to be touched.
- `Determinism Gate`: Triggered — code-health artifact discovery and summary
  rendering must be deterministic from repo-local files and the current branch
  diff.
- `LLM Budget/Safety Gate`: Triggered — the prompt should become more specific
  by reusing existing deterministic summaries, not by inflating provider work
  or token volume unnecessarily.
- `Observability Gate`: Triggered — operators should be able to tell from the
  prompt contract and docs that local review now checks for structural slop in
  changed files.

## Shared Workflow/Policy Change Checklist (Only If Applicable)

- Callers depending on this shared behavior:
  - `tools/horadus/python/horadus_workflow/task_workflow_local_review.py`
  - `tools/horadus/python/horadus_workflow/_task_workflow_local_review_provider.py`
  - `tools/horadus/python/horadus_cli/task_workflow_core.py`
  - `docs/AGENT_RUNBOOK.md`
  - `tests/horadus_cli/v2/test_task_local_review.py`
  - `tests/workflow/test_task_workflow.py`
- Add at least one regression test that proves unaffected provider-adapter or
  workflow-caller behavior still passes while the prompt contract gets richer.
- Current semantics to preserve:
  - The first non-empty line remains the repo-owned
    `HORADUS-LOCAL-REVIEW: findings|no-findings` marker for prompt-only
    providers.
  - Findings remain concise and ordered by severity with file paths when
    possible.
  - Codex keeps its native `review --base` flow, with Horadus normalizing the
    result into the same local-review surface.

## Acceptance Criteria

- [ ] The local-review prompt explicitly asks reviewers to flag hotspot
      expansion, multi-concern growth inside touched modules, and verbosity or
      duplication regressions in addition to ordinary bugs, regressions, and
      missing tests
- [ ] When changed-file code-health output is available, local review includes
      a bounded summary of that signal instead of asking providers to rediscover
      it from the diff alone
- [ ] Existing marker-line output normalization and findings-first formatting
      remain stable across providers
- [ ] Tests cover prompt rendering, code-health artifact reuse, and an
      unaffected provider-adapter path without network access

## Validation

- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/v2/test_task_local_review.py tests/workflow/ -v -m unit`
- `make test-integration-docker`
- `make agent-check`
- `uv run --no-sync horadus tasks local-gate --full`
