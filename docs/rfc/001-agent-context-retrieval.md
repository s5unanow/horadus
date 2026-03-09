# RFC-001: Markdown-First Context Retrieval for Agent Workflow

**Status**: Proposed  
**Date**: 2026-03-09  
**Authors**: Codex + repo operator

## Why This Is an RFC

This document is an RFC rather than an ADR because it captures an active design
investigation with multiple viable implementation paths and no final decision
yet. If Horadus adopts a concrete retrieval architecture, that accepted choice
should later be recorded in an ADR.

## Problem

The current agent context surface mixes implementation-critical material with
bookkeeping and historical ledgers.

High-signal context for implementation work usually means:

- the active task spec
- the exact code files likely to change
- the exact test files that validate the behavior
- the minimal workflow policy needed for the current phase

Low-signal or bookkeeping-heavy context often includes:

- broad sprint queue history
- completed-task ledgers
- broad project narrative/status summaries
- superseded specs or stale task assumptions
- generic command boilerplate repeated in multiple places

That noise does not usually change the implementation result, but it does slow
orientation, increase edit surface area, and make stale assumptions easier to
carry into execution.

## Goals

- Keep Markdown as the primary authoring format
- Make implementation context smaller and more precise
- Avoid pulling superseded or low-value task records into default coding context
- Support deterministic retrieval for task specs and policy sections
- Stay compatible with future retrieval/file-search or MCP-based workflows

## Non-Goals

- Replacing Markdown with a new authoring format
- Building a full external search service immediately
- Solving every repository documentation problem in the first slice

## Findings

### Markdown Is Good Enough

Markdown is already a strong source format for retrieval because it has natural
section boundaries: headings, paragraphs, lists, and code fences. It works well
for semantic and keyword retrieval, and it is already supported by hosted
retrieval/file-search systems.

Conclusion: Horadus does not need a new source format.

### Plain Markdown Alone Is Not Precise Enough

Markdown headings are good chunk boundaries, but they are not stable,
machine-governed IDs. If exact section retrieval matters, raw headings alone
are not sufficient.

Conclusion: keep Markdown, but add lightweight metadata and revision-local
deterministic chunk IDs.

### The Current Structured Task Context Is Too Broad For Implementation Mode

The current Horadus structured task surfaces, especially `context-pack`,
include backlog text, sprint status, spec template, likely code areas, and
generic workflow commands. That is useful as a general summary, but it is
broader than necessary for active implementation work.

Conclusion: the current `context-pack` should support narrower modes.

## Recommended Direction

Target architecture:

1. YAML front matter for document metadata
2. section-level chunking by Markdown heading
3. generated deterministic chunk identifiers
4. retrieval modes tuned to the task phase
5. explicit supersession metadata so stale specs are excluded by default

Near-term phase-1 deliverable:

- keep Horadus CLI as the retrieval entry point
- add a narrower `context-pack --mode implement --format json` payload
- add only the metadata and parsing needed to make that narrower payload
  deterministic

Section-level indexing and chunk-ID machinery remain the target architecture for
later phases, not a requirement to ship the first implementation slice.

## Proposed Document Schema

### YAML Front Matter

Recommended baseline schema:

```yaml
---
doc_id: task-276-spec
doc_type: task_spec
task_id: TASK-276
status: active
superseded_by: null
scope: implementation
canonical: true
retrieval_ready: true
section_contract: task_spec_v1
tags: [workflow, cli, review-gate]
owner: repo
---
```

### Required Fields By Document Type

**Task spec**

- `doc_id`
- `doc_type: task_spec`
- `task_id`
- `status`
- `canonical`
- `retrieval_ready`
- `section_contract` when `retrieval_ready: true`
- `superseded_by` when `status: superseded`

**Policy doc**

- `doc_id`
- `doc_type: policy_doc`
- `status`
- `scope`
- `retrieval_ready`
- `section_contract` when `retrieval_ready: true`
- `superseded_by` when `status: superseded`

Near-term note: policy-doc front matter is a target contract, not a phase-1
repo-wide requirement. Phase 1 policy retrieval should work from an explicit
CLI-curated allowlist of legacy docs, with front matter added incrementally as
those docs are touched or formally migrated.

**Execution plan**

- `doc_id`
- `doc_type: exec_plan`
- `task_id`
- `status`
- `retrieval_ready`
- `section_contract` when `retrieval_ready: true`
- `superseded_by` when `status: superseded`

### Status Values

- `active`
- `superseded`
- `archived`

Rules:

- `active` documents are eligible for consideration in default retrieval
- `superseded` documents are excluded by default
- `archived` documents are excluded from implementation retrieval

Status is only one eligibility input. Final inclusion still depends on the
selected retrieval mode and, where applicable, the retrieval-ready contract or
explicit fallback rules such as whole-document inclusion or the curated legacy
policy registry.

Document `status` is the lifecycle of the document itself, not the lifecycle of
the task. For task-linked documents such as `task_spec` and `exec_plan`, task
lifecycle should be resolved separately as derived `task_status` using the
repo's existing task states (`active|backlog|completed`) from the authoritative
task ledgers and parsers, not duplicated as author-maintained front matter.

Examples:

- a canonical spec for a backlog task can be `status: active` and
  derived `task_status: backlog`
- a canonical spec for a completed task can still be `status: active` and
  derived `task_status: completed` if it remains the current historical
  reference
- a replaced spec becomes `status: superseded` regardless of task state

Default implementation retrieval should treat these fields differently:

- filter task-linked docs by both `status: active` and `task_status: active`
- treat `task_status: backlog|completed` docs as non-default history/triage
  material unless a caller explicitly asks for them
- surface autonomous eligibility separately from task status; tasks marked
  `[REQUIRES_HUMAN]` should be labeled `autonomous_eligible: false` (or
  equivalent) from the sprint/task ledgers and excluded or prominently flagged
  in default autonomous `implement` mode

Supersession should also be explicit:

- `superseded_by` is required when `status: superseded`
- `superseded_by` should be `null` or omitted for `status: active|archived`

### Scope Values

`scope` is required for `policy_doc` and optional for other document types.

Recognized phase-oriented scope values:

- `implementation`
- `finish`
- `triage`
- `shared`

Mode expectations:

- `implement` mode should prefer policy docs with `scope: implementation` and
  may also include `scope: shared`
- `finish` mode should prefer policy docs with `scope: finish` and may also
  include `scope: shared`
- `triage` mode should prefer policy docs with `scope: triage` and may also
  include `scope: shared`
- `deep` mode may include any scope

### Retrieval-Ready Contract

`retrieval-ready` is a normative metadata state, not an informal label.

A document is retrieval-ready only when all of the following are true:

- it has the required front matter for its `doc_type`
- `retrieval_ready: true` is set explicitly
- `section_contract` names a recognized type-specific contract
- the document body satisfies that named section contract

Near-term recognized section contracts:

- `task_spec_v1`
- `exec_plan_v1`
- `policy_doc_v1`

Allowlist membership alone does not make a document retrieval-ready. During
migration, the curated legacy policy allowlist is a fallback source for
retrieval, not a substitute for the retrieval-ready contract.

For phase 1, the minimum section contracts are:

- `task_spec_v1`: `Problem Statement`, `Inputs`, `Outputs`, `Non-Goals`,
  `Acceptance Criteria`, `Validation`
- `exec_plan_v1`: conformance to the richer `tasks/exec_plans/TEMPLATE.md`
  contract, including status, goal, inputs, outputs, scope, living plan,
  decisions, risks, validation commands, and notes/links
- `policy_doc_v1`: purpose/scope, operative rules, and validation or usage
  notes

Legacy documents that do not meet this contract remain eligible only for
fallback retrieval modes such as whole-document inclusion or curated allowlist
lookup.

## Chunking And Indexing Model

### Chunk Boundary Rules

Index Markdown by heading section, not as whole files.

For ledger-style docs that keep many task records under one heading, heading
chunks alone are not precise enough. `tasks/CURRENT_SPRINT.md` is the main
example: the `Active Tasks` section should be further split by task line or
task block so retrieval can target the current task without pulling the full
active queue.

Phase-1 rule:

- use heading chunks as the default
- add doc-specific sub-section extractors for high-noise ledger docs such as
  `tasks/CURRENT_SPRINT.md`
- key those sub-chunks by document path, parent heading, and task identifier or
  list ordinal
- include not only the active-task line/block, but also task-scoped blocker
  metadata and any relevant sprint-scope constraints carried in adjacent
  sections when they apply to the requested task

Each chunk should store:

- `chunk_id`
- `path`
- `doc_id`
- `doc_type`
- `task_id` for task-linked documents
- `status`
- derived `task_status` for task-linked documents
- derived `autonomous_eligible` for task-linked documents
- `canonical` for task-linked spec documents
- `retrieval_ready`
- `scope` for policy documents
- `fallback_source` when the chunk came from a legacy fallback path such as the
  curated policy registry or whole-document legacy inclusion
- `heading_path`
- `section_level`
- `ordinal`
- `text`

This metadata can either live directly on each chunk record or in a
document-metadata table joined by `doc_id`, but the effective retrieval layer
must expose it alongside chunks so mode filters can be applied without
re-parsing source files at query time.

### Deterministic Chunk IDs

Generate `chunk_id` from:

- relative file path
- heading hierarchy
- ledger sub-key (`task_id` when present for ledger/task sub-chunks, otherwise
  section ordinal)

Recommended implementation: `sha1(path + heading_path + ledger_sub_key)`.

These IDs are deterministic for a given document shape, but they are not stable
across normal edits such as heading renames, section moves, or inserted
sections. This avoids forcing authors to maintain manual anchors for every
section while keeping chunk references reproducible within a given revision.
They are appropriate for local indexing and short-lived retrieval handles, not
as long-lived cross-revision citations on their own.

For normal heading chunks, `ledger_sub_key` is the section ordinal. For
ledger-style sub-chunks such as `tasks/CURRENT_SPRINT.md` task extracts,
`ledger_sub_key` should prefer the task identifier when available and fall back
to ordinal only when no stronger per-item key exists.

### Optional Explicit Anchors

Manual anchors are still useful for a small number of hot, frequently cited
policy sections. They should be used sparingly, not as a repo-wide requirement.
Use them when the repo needs durable references across revisions, such as
long-lived citations or stable MCP resource identifiers.

## Retrieval Modes

### `implement`

Default for coding tasks. Include only:

- the canonical spec for the requested task where `status: active` and
  `task_status: active`
- only autonomous-eligible tasks by default for autonomous execution flows; if a
  task is human-gated, `implement` mode should either exclude it or return it
  with an explicit blocked/human-gated marker
- declared task paths from the task record, treated as candidate code/doc paths
  unless a stronger path classification exists
- exact test paths only when a structured source of truth exists for them;
  otherwise emit derived test candidates produced by a deterministic repo-local
  heuristic
- minimal workflow policy for the active phase, preferring code-backed policy
  surfaces over Markdown summaries when both exist

`implement` mode intentionally diverges from the current broad orientation order
to reduce noise. It should still include compact orientation chunks for
`tasks/CURRENT_SPRINT.md`, `docs/ARCHITECTURE.md`, and `docs/DATA_MODEL.md`, or
be paired with a separate lightweight orientation payload that supplies that
material before implementation starts. Excluding the full `PROJECT_STATUS.md`
narrative from default `implement` retrieval is a deliberate narrowing of
current guidance, trading broad milestone narrative for a smaller execution
payload; operationally relevant status facts may still be surfaced through
compact orientation metadata rather than the whole document.

Exclude by default:

- `tasks/COMPLETED.md`
- `PROJECT_STATUS.md`
- superseded specs
- archived docs
- broad sprint history

### `finish`

Focused only on:

- finish/lifecycle policy
- review-gate semantics
- merge/sync verification steps

### `triage`

Focused on:

- backlog entries
- current sprint active queue
- triage policy

### `deep`

Opt-in mode that may include:

- architecture docs
- runbooks
- broader policy or historical context

## Context-Pack Changes

Add a narrower CLI surface:

- `horadus tasks context-pack TASK-XXX --mode implement --format json`

Here, `--mode implement` is the new surface. `--format json` already exists and
should remain the structured output form for agent consumption.

Recommended `implement` payload:

- task metadata
- orientation chunks or a separate orientation payload covering compact
  `CURRENT_SPRINT`, `ARCHITECTURE`, and `DATA_MODEL` context
- execution-plan content: retrieval-ready exec-plan chunks when available, or a
  legacy whole-plan / direct-file side input for tasks that require a living
  exec plan under repo policy
- active spec chunks when the spec follows the retrieval-ready contract, or
  whole-spec / best-effort mapped spec content for legacy specs
- declared task paths, with optional later classification into code/doc/test
  path types
- exact test paths when a structured source of truth exists, otherwise labeled
  derived test candidates
- policy statements from code-backed workflow surfaces first, plus supporting
  policy chunks from retrieval-ready policy docs or an explicit curated policy
  allowlist during migration
- excluded sources

In phase 1, `derived test candidates` should be a concrete, deterministic
fallback rather than a free-form guess. Because the current task record does not
store canonical test-file metadata, most tasks will likely use this fallback
until a stronger structured source is added. The fallback contract should be:

- normalize raw backlog `**Files**:` entries into machine-usable declared paths
  first by stripping backticks, dropping parenthetical qualifiers, and
  classifying file-vs-directory paths on a best-effort basis
- derive candidates from those normalized declared paths when present
- search repo-standard test locations for matching module stems or adjacent
  package tests
- return them as labeled candidates with a `match_reason`
- keep them separate from exact test metadata in the output shape

In phase 1, legacy spec fallback selection also needs a deterministic rule.
Because current code only exposes `spec_paths` as filename-glob matches, the
selection contract should be:

- parse the backlog `**Spec**:` line as structured task metadata and treat it as
  the primary legacy-spec selector when present
- if no structured spec reference exists, accept legacy fallback only when
  exactly one matching spec file exists
- if multiple legacy candidates remain after those checks, fail closed as an
  ambiguous canonical-spec condition rather than picking by filename order

Likewise, the curated legacy policy allowlist should be an explicit repo-owned
registry of paths used during migration. It should not rely on implicit globbing
or ad hoc document discovery. The preferred implementation is a dedicated
implement-mode policy registry defined alongside the existing workflow metadata
in `src/core/repo_workflow.py`, not reuse of the broader workflow/completion
reference-path tuples that include README/skill-oriented material.

For workflow/completion/fallback policy, retrieval must follow the repo's
existing source-of-truth hierarchy rather than invent a new one. The effective
policy view should:

- respect `AGENTS.md` precedence, with runtime/code truth above docs
- treat `AGENTS.md` plus canonical runbook/docs as the normative policy sources
- use `src/core/repo_workflow.py` for executable command metadata and the narrow
  code-backed policy fragments it already owns
- combine those sources into a smaller implementation payload without claiming
  that `repo_workflow.py` replaces the broader repo policy contract

If the repo later wants a single mechanically authoritative policy surface, that
would require a separate consolidation/parity effort and is outside this RFC's
phase-1 scope.

The current broad human-readable mode should remain the default unflagged CLI
output in phase 1 for compatibility. `--mode implement` is the explicit
surface for narrower agent retrieval. To actually reduce default autonomous
agent noise, the canonical agent-facing workflow surfaces should be updated in
the same slice to call the implement-mode variant for implementation work, even
if the raw unflagged CLI output remains unchanged for humans.

This work should extend Horadus's existing structured task surfaces first
(`show`, `search`, and `context-pack`) rather than bypassing them with an
entirely separate retrieval entry point.

## Validation And Guardrails

Add a docs/context validation step with mixed severity:

- fail for retrieval-ready docs when required front matter is missing
- fail when task-linked retrieval-ready docs cannot be resolved to a derived
  `task_status` of `active|backlog|completed` from the authoritative task
  ledgers
- fail when autonomous execution retrieval cannot resolve whether a task is
  human-gated / autonomous-eligible from the authoritative sprint/task ledgers
- fail when more than one candidate canonical task spec exists for a task across
  retrieval-ready specs and legacy fallback specs that would participate in
  phase-1 implement retrieval
- fail when legacy fallback selection cannot identify a single canonical spec
  using the structured backlog spec reference or the single-match fallback rule
- fail when `status: active` and `superseded_by` are both set inconsistently on
  retrieval-ready docs
- fail when `retrieval_ready: true` is set but `section_contract` is missing,
  unknown, or not satisfied by the document body

For sprint-active tasks without a spec today, use a phased rule instead of a
hard fail:

- near-term: warn when a sprint-active implementation task has no canonical
  active spec
- later: consider fail-closed enforcement only for tasks created after an
  agreed migration cutoff or tasks explicitly marked retrieval-ready

For legacy specs that predate the metadata contract:

- near-term: allow no-front-matter legacy specs to continue working through
  whole-spec inclusion or best-effort parsing
- later: tighten enforcement only after a documented migration cutoff

Add a retrieval hygiene rule:

- superseded specs must never appear in default implementation context

## Implementation Options

### Option 1: Extend Existing Structured Horadus Commands First

Extend `show`, `search`, and especially `context-pack` so they emit smaller,
mode-specific structured payloads, but do not build a local index yet.

**Pros**

- fastest to ship
- lowest complexity
- aligned with current repo policy preferring Horadus CLI + JSON
- no new indexing layer

**Cons**

- less flexible for future retrieval
- weaker support for exact section targeting
- harder to rank/filter chunks mechanically

### Option 2: Local Markdown Index Behind Existing Commands

Build a repo-local parser/indexer that reads Markdown front matter and heading
sections, then have existing Horadus commands retrieve from that index.

**Pros**

- best balance of precision and simplicity
- deterministic section filtering
- no external dependency required
- naturally compatible with current repo workflow

**Cons**

- requires initial indexing code and validation rules
- more work than a simple output trim

### Option 3: Hosted Retrieval/File-Search Back End

Push the docs into a hosted retrieval layer and query that directly.

**Pros**

- powerful semantic retrieval
- built-in ranking/filtering
- future-friendly for larger corpora

**Cons**

- adds service coupling
- weaker repo-local determinism
- probably too much infrastructure for the current problem

### Option 4: MCP Resource Layer

Expose task/spec sections as MCP resources or resource templates.

**Pros**

- clean long-term model for structured context access
- good fit if the repo already grows more tool-driven

**Cons**

- not the fastest first step
- still needs document structure and chunking rules underneath

## Recommendation

Adopt **Option 1** as the near-term target and treat **Option 2** as the next
step if the narrower structured payload still proves insufficient:

- keep Horadus CLI as the primary structured retrieval surface
- add `context-pack --mode implement --format json`
- reduce implementation payloads to task metadata, relevant spec/code/test
  paths, and minimal policy context
- add front matter and supersession metadata for new/updated specs
- exclude superseded/bookkeeping docs by default

Prepare for **Option 2** by keeping the document schema and chunking model
compatible with a future local index:

- keep Markdown
- chunk by heading section when indexing is added
- generate deterministic chunk IDs
- preserve compatibility with later MCP or hosted retrieval integration

Then treat hosted retrieval or MCP integration as a later delivery path, not a
prerequisite for fixing the current noise problem.

## Proposed Rollout

### Phase 1

- add `context-pack --mode implement --format json`
- make `show` and `context-pack` payloads explicitly mode-aware without changing
  the default unflagged CLI output yet
- enumerate and update every current caller of the plain
  `horadus tasks context-pack TASK-XXX` implementation workflow surface before
  switching autonomous flows, following the shared-workflow caller-audit rule
- update the canonical agent-facing workflow surfaces and registries that
  currently reference plain `context-pack`, including `AGENTS.md`, `README.md`,
  `docs/AGENT_RUNBOOK.md`, `ops/skills/horadus-cli/SKILL.md`,
  `ops/skills/horadus-cli/references/commands.md`, and the workflow reference
  metadata in `src/core/repo_workflow.py`, so autonomous implementation flows
  use the implement-mode context-pack entry point instead of the legacy broad
  default
- add parity/regression tests for at least one unaffected caller and one
  updated canonical caller so the shared-workflow change does not silently
  leave some surfaces on the old broad contract
- keep `search` unchanged in phase 1 except for any minimal compatibility
  adjustments needed to support the narrower structured retrieval flow
- derive and expose autonomous eligibility for task-linked retrieval from the
  existing `[REQUIRES_HUMAN]` markers in the sprint/task ledgers
- parse backlog `**Spec**:` lines as structured task metadata so legacy spec
  fallback can resolve a canonical source deterministically
- add front matter to new or touched task specs
- update `tasks/specs/TEMPLATE.md` to include the new front-matter contract
- use explicit `retrieval_ready: true` plus `section_contract` only on specs
  that satisfy the retrieval-ready contract
- add supersession metadata rules for specs that are revised or replaced
- resolve `task_status` for task-linked docs from the existing task ledgers at
  retrieval/index time rather than adding it as author-maintained front matter
- normalize backlog `**Files**:` entries into declared-path metadata before
  deriving test candidates from them
- defer retrieval-ready `exec_plan` adoption to phase 2 unless
  `tasks/exec_plans/TEMPLATE.md` is updated in the same slice
- use whole-spec inclusion or best-effort section mapping for legacy specs that
  do not yet follow the retrieval-ready contract
- define and ship the phase-1 `derived_test_candidates` output contract,
  including labeled candidate paths and `match_reason`
- define and ship the phase-1 code-backed policy payload contract, including
  which statements and reference-path registries are emitted from
  `src/core/repo_workflow.py`
- source policy retrieval from an explicit curated allowlist of legacy policy
  docs until policy-doc front matter is introduced more broadly
- define that curated legacy policy allowlist as an explicit repo-owned registry
  before wiring it into `implement` mode, preferably by extending
  `src/core/repo_workflow.py`
- add a doc-specific extractor for `tasks/CURRENT_SPRINT.md` so `implement`
  mode can retrieve the active task line/block, associated blocker metadata,
  and relevant sprint-scope constraints without pulling the full sprint file
- for tasks that require a living exec plan under current repo policy, include
  the existing exec-plan file as a mandatory side input even before
  retrieval-ready exec-plan contracts are adopted

### Phase 2

- build local section indexing behind the existing Horadus commands
- add doc metadata validation gate
- update `tasks/exec_plans/TEMPLATE.md` and enable retrieval-ready `exec_plan`
  validation if phase 1 deferred that contract
- keep spec-presence enforcement warn-only unless the repo completes a spec
  migration or adopts a retrieval-ready marker
- refine the phase-1 derived-test and legacy-policy fallback contracts only if
  local indexing or broader policy-doc migration needs richer metadata
- decide whether to expand front matter to policy docs broadly or keep a
  curated policy-doc registry

### Phase 3

- evaluate MCP or hosted retrieval integration if needed

## Open Questions

- Should all policy docs get front matter immediately, or only task specs first?
- Should `tasks/CURRENT_SPRINT.md` be surfaced in `implement` mode as a compact
  task-scoped extract, a separate orientation payload, or both, while
  preserving its current authoritative role in repo policy?

## References

- OpenAI prompting: https://platform.openai.com/docs/guides/prompting
- OpenAI file search: https://developers.openai.com/api/docs/guides/tools-file-search
- GitHub Flavored Markdown spec: https://github.github.io/gfm/
- GitHub Markdown syntax and anchors: https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax
- GitHub YAML front matter guidance: https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter
- Anthropic prompt templates and variables: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables
- Model Context Protocol resources: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
