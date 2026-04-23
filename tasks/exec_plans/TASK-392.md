# TASK-392: Fix root horadus help and runbook freshness drift

## Status

- Owner: Codex
- Started: 2026-04-22
- Current state: Local validation passed; finish lifecycle pending
- Planning Gates: Required — the task changes shared CLI/operator surfaces and docs freshness enforcement.

## Goal (1-3 lines)

Bring root `horadus` help output and the runbook command index back into sync while ensuring
runbook freshness drift cannot hide behind missing enforcement.

## Inputs

- Spec/backlog references: `tasks/BACKLOG.md` (`TASK-392`)
- Runtime/code touchpoints: `docs/AGENT_RUNBOOK.md`, `tools/horadus/python/horadus_workflow/docs_freshness.py`, `tools/horadus/python/horadus_cli`
- Preconditions/dependencies: inventory the advertised root command surface and current docs freshness marker coverage before edits

## Outputs

- Expected behavior/artifacts: aligned root help/runbook command surfaces plus freshness enforcement that covers the runbook marker path
- Validation evidence: CLI/workflow regression coverage, docs verification, and canonical repo gates

## Non-Goals

- Explicitly excluded work: expanding the CLI beyond the already intended root command surface or rewriting unrelated operator docs

## Scope

- In scope: root help alignment, runbook command index updates, freshness enforcement, and focused regression tests
- Out of scope: unrelated docs cleanup outside the command-surface and freshness-drift contract

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: reconcile the existing root command surface and extend freshness checks only where the runbook marker currently escapes enforcement.
- Rejected simpler alternative: refresh the runbook text alone without binding it to the live CLI surface or freshness checks.
- First integration proof: run the affected CLI/workflow unit suites and the canonical local gate after the help surface and freshness checks agree.
- Hotspot Outcome: keep-flat-with-rationale — the task must touch existing shared CLI and docs-freshness hotspots to correct a live operator-facing contract.
- Waivers: none.

## Plan (Keep Updated)

1. Preflight (branch, tests, context) - done
2. Implement - done
3. Validate - done
4. Ship (PR, checks, merge, main sync) - in progress

## Decisions (Timestamped)

- 2026-04-22: Seed an exec plan before implementation because the task touches shared CLI/help and workflow-freshness enforcement paths. (reason: hotspot-backed workflow work needs a documented safe shape before edits)
- 2026-04-23: Keep the root help surface as the source for command-group descriptions and add tests that require the runbook to mention every advertised root command. (reason: this catches the observed operator-facing drift without introducing a generated-doc pipeline)

## Risks / Foot-guns

- Help text and runbook can drift again if only one source is updated -> keep the live command surface and freshness enforcement linked in tests.
- Small CLI/help changes can affect many callers -> prefer the smallest contract-preserving delta and add focused regressions.

## Validation Commands

- `uv run --no-sync pytest tests/horadus_cli/v2/test_app.py tests/workflow/test_docs_freshness.py -v -m unit`
- `make typecheck`
- `uv run --no-sync pytest tests/horadus_cli/ tests/workflow/ -v -m unit`
- `make agent-check`
- `make test-integration-docker`
- `uv run --no-sync horadus tasks local-review --format json`
- `uv run --no-sync horadus tasks local-gate --full`

## Notes / Links

- Spec: none yet
- Relevant modules: `tools/horadus/python/horadus_cli`, `tools/horadus/python/horadus_workflow/docs_freshness.py`, `docs/AGENT_RUNBOOK.md`
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
