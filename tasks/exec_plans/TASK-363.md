# TASK-363: Add Behavior-Oriented Eval Suites for High-Risk LLM Safety Paths

## Status

- Owner: Codex
- Started: 2026-04-06
- Current state: In progress
- Planning Gates: Required — shared eval harness and release-gate behavior across prompt/runtime surfaces

## Goal (1-3 lines)

Add a deterministic behavior-eval layer that measures specific production
contracts the gold-set benchmark does not encode directly. Ship targeted suites
for taxonomy safety, degraded-mode provisional writes, and report grounding,
with CLI support for running only the needed subset.

## Inputs

- Spec/backlog references:
  `tasks/BACKLOG.md` `TASK-363`, `tasks/CURRENT_SPRINT.md`
- Runtime/code touchpoints:
  `src/eval/`, `tools/horadus/python/horadus_cli/`,
  `tools/horadus/python/horadus_app_cli_runtime.py`, `src/storage/event_extraction.py`,
  `src/processing/trend_impact_mapping.py`, `src/core/report_runtime.py`
- Preconditions/dependencies:
  guarded task branch start completed via `horadus tasks safe-start`

## Outputs

- Expected behavior/artifacts:
  a repo-owned `horadus eval behavior` command, timestamped behavior-eval JSON
  artifacts, tagged suites for taxonomy safety / degraded-mode safety / report
  grounding, and operator docs describing when to run them alongside benchmark
- Validation evidence:
  unit coverage for the new eval runner and CLI/runtime bridge, then canonical
  repo gates (`make agent-check`, targeted unit suites, `local-gate --full`)

## Non-Goals

- Explicitly excluded work:
  new LLM-scored gold-set rows, changing release thresholds, or replacing the
  existing benchmark/audit/taxonomy workflow

## Scope

- In scope:
  deterministic scenario runner, contract-tag metadata, targeted CLI filters,
  docs for promotion/review workflow, and task-ledger updates
- Out of scope:
  runtime behavior changes to taxonomy mapping, provisional extraction, report
  generation, or semantic-cache policy unless required to support the eval

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape:
  run behavior suites against existing deterministic/runtime helper surfaces so
  failures map to concrete production contracts without requiring live model
  calls
- Rejected simpler alternative:
  encode these contracts only as ad hoc unit tests; rejected because the task
  needs a repo-owned eval surface and targeted operator-facing CLI workflow
- First integration proof:
  `uv run --no-sync horadus eval behavior --suite taxonomy-safety --format json`
- Waivers:
  None currently

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
2. Implement behavior-eval runner + suites
3. Wire CLI/runtime + docs + tests
4. Validate
5. Ship (PR, checks, merge, main sync)

## Decisions (Timestamped)

- 2026-04-06: Use a deterministic behavior-eval harness instead of extending
  the gold-set benchmark because the target contracts are runtime-safety
  invariants, not comparative model-quality metrics.
- 2026-04-06: Support targeted execution with suite/tag filters so release and
  prompt workflows can run only the relevant behavior checks without paying the
  cost of the full benchmark path.

## Risks / Foot-guns

- Behavior evals can drift into duplicative unit tests -> keep scenarios small,
  contract-labeled, and operator-runnable through one CLI entry point.
- CLI/runtime changes can break existing eval command wiring -> add parser,
  runtime bridge, and command tests rather than relying on manual smoke checks.
- Docs can overstate required gates -> only document suites actually shipped in
  this task and keep the benchmark as a separate complementary gate.

## Validation Commands

- `uv run --no-sync pytest tests/unit/eval/ -v -m unit`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make typecheck`
- `make agent-check`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`
- `make test-integration-docker`

## Notes / Links

- Spec: backlog-only task, no dedicated spec
- Relevant modules:
  `src/processing/trend_impact_mapping.py`,
  `src/storage/event_extraction.py`,
  `src/core/report_runtime.py`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
