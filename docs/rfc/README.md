# RFC Authoring And Review Checklist

Use this checklist before circulating an RFC for review and again before
calling it ready for implementation planning.

## Contract Checks

- Source-of-truth: does the RFC match the current precedence in `AGENTS.md`,
  runtime code, ledgers, and docs?
- Current reality: do the proposed contracts match the actual CLI output,
  parser behavior, and stored metadata that exist today?
- Legacy fallback: does the RFC define deterministic behavior for dirty or
  incomplete legacy data?
- Eligibility: does the RFC handle `[REQUIRES_HUMAN]`, blocked states, and any
  other task-eligibility constraints that affect autonomous execution?
- Templates: if the RFC introduces a new document contract, does it update the
  relevant templates or explicitly defer them?
- Migration: does the rollout say how legacy docs/data move toward the new
  contract without breaking current workflows?

## Scope Checks

- Phase split: is phase 1 clearly separated from the longer-term target
  architecture?
- Defaults: if a new surface is opt-in, does the RFC also say how the canonical
  default workflow changes, if that is required to realize the benefit?
- Payload shape: does every required retrieval rule have corresponding fields in
  the proposed payload/index metadata?
- Orientation: if the RFC narrows context, does it preserve the minimum
  orientation inputs the repo still requires?

## Precision Checks

- Canonical selection: if multiple files can match, does the RFC define how one
  canonical input is selected or when the system must fail closed?
- Determinism vs stability: does the RFC distinguish revision-local identifiers
  from long-lived stable references?
- Validation: are validation rules scoped correctly for phase 1 vs migrated
  docs, and do they match the actual data model?
- Terminology: are words like `active`, `canonical`, `ready`, `exact`, and
  `default` defined precisely enough to avoid conflicting interpretations?

## Review Prompt

When requesting review, explicitly ask reviewers to challenge:

- source-of-truth conflicts
- current CLI/data-model mismatches
- legacy-data assumptions
- human-gated/task-eligibility behavior
- template and migration gaps
- phase-1 vs end-state ambiguity
