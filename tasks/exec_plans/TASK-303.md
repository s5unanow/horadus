# TASK-303: Extract Repo Workflow Into a Dedicated Tooling Home

## Status

- Owner: Codex
- Started: 2026-03-11
- Current state: Done
- Planning Gates: Required — architecture/boundary refactor across CLI, scripts, and repo workflow helpers

## Goal (1-3 lines)

Move repo workflow logic out of mixed CLI/app locations into one dedicated,
self-contained tooling/workflow home with a documented interface. Leave CLI
modules as thin adapters and keep app/runtime packages isolated from repo
workflow.

## Inputs

- Spec/backlog references:
  - `tasks/BACKLOG.md` (`TASK-303`)
  - `AGENTS.md` workflow and task-lifecycle policy
- Runtime/code touchpoints:
  - `src/horadus_cli/`
  - `scripts/`
  - `src/core/docs_freshness.py`
  - `docs/AGENT_RUNBOOK.md`
  - `AGENTS.md`
  - `docs/ARCHITECTURE.md`
  - `tests/horadus_cli/`
  - `tests/unit/scripts/`
  - `tests/unit/core/test_docs_freshness.py`
- Preconditions/dependencies:
  - keep the external `horadus` command surface stable
  - workflow code must not import CLI or app/runtime packages
  - app/runtime packages must not gain new dependencies on repo workflow
  - resolve current CLI-result-type coupling before moving workflow owners: workflow must not keep depending on CLI-owned result types
  - do not choose a Python-`src`-only home if the CLI/workflow will likely be reimplemented in Go
  - treat `scripts/` as an entrypoint/wrapper surface only, not a permanent ownership home for workflow logic
  - do not break the current build/install/coverage contract while the implementation is still Python-backed
  - preserve zero-install bootstrap entrypoints that run from raw checkout with `python3` before dependency install
  - preserve the current versioned-shell compatibility contract unless a separate follow-up task explicitly changes it
  - replace path-depth-based repo-root resolution with a stable contract before moving owner modules deeper

## Outputs

- Expected behavior/artifacts:
  - one dedicated, language-neutral tooling/workflow home, tentatively `tools/horadus/`
  - one explicit interim Python layout inside that home so the current repo can import/test workflow code before any Go rewrite
  - CLI modules reduced to parser/routing/rendering adapters over workflow APIs
  - workflow scripts reduced to thin wrappers over workflow entrypoints
  - docs/task/PR governance logic removed from `src/core/`
  - workflow-owned tests moved out of app-core/CLI-owned test locations into a dedicated workflow test surface
  - packaging/install/coverage config updated so extracted Python workflow code is still installed, imported, and measured under the existing gate model
  - zero-install workflow guard scripts remain runnable directly from checkout with system Python only
  - lint/typecheck/security/build/local-gate/CI configuration updated so the extracted workflow home stays inside the enforced repo gate surface
  - stable ownership/entrypoint docs updated to reflect the extracted workflow home and CLI/script adapter roles
- Validation evidence:
  - import-boundary tests proving workflow is self-contained
  - CLI regression tests proving command behavior is unchanged
  - test-tree ownership proving workflow tests are no longer parked under app-core by default
  - local hooks/gates green after the migration

## Non-Goals

- Explicitly excluded work:
  - changing user-facing `horadus` command names or output contracts
  - moving product/backend runtime logic out of `src/api`, `src/core`, `src/storage`, `src/processing`, `src/ingestion`, or `src/workers`
  - rebuilding workflow behavior contracts while moving code
  - introducing multiple overlapping tooling packages

## Scope

- In scope:
  - define the permanent tooling/workflow ownership boundary
  - move repo workflow modules out of CLI/app ownership
  - extract the initial repo-workflow set only:
    - task lifecycle and ledger handling
    - triage/intake workflow
    - PR/review/closure workflow guards
    - docs-freshness workflow logic
    - workflow-policy helpers currently in `src/core/repo_workflow.py`
  - document and enforce the CLI↔workflow contract
  - convert repo scripts into workflow wrappers
  - split tests into workflow-vs-CLI-vs-app ownership where needed
- Out of scope:
  - feature work unrelated to repo workflow packaging
  - app/business-logic refactors outside dependency-boundary cleanup
  - speculative package splits beyond app / workflow / CLI
  - reorganizing non-workflow operational CLI surfaces unless they are needed only to preserve imports during the extraction

## Gate Outcomes / Waivers

- Accepted design / smallest safe shape: create one dedicated tooling/workflow home and move existing logic into it, keeping CLI as the only public interface layer.
- Rejected simpler alternative: leaving workflow logic scattered across CLI modules, scripts, and `src/core` preserves the current ownership ambiguity.
- First integration proof: canonical `horadus tasks ...` and repo guard scripts still pass while importing workflow logic through the new tooling/workflow home only.
- Waivers: exact folder/module names may change during implementation, but the final ownership rules may not.

## Plan (Keep Updated)

1. Preflight (branch, tests, context)
   - inventory every repo workflow surface and current import edge
   - enumerate every known shared-helper caller before moving code, including:
     - `scripts/check_pr_closure_state.py`
     - `scripts/check_pr_review_gate.py`
     - `scripts/check_docs_freshness.py`
     - `tests/horadus_cli/shell/test_cli_versioning.py`
     - `tests/unit/core/test_repo_workflow.py`
     - `tests/unit/core/test_docs_freshness.py`
     - `tests/unit/scripts/test_check_pr_review_gate.py`
     - task CLI and triage CLI callers inside `src/horadus_cli/`
     - local-gate/pr-finish command builders in `src/horadus_cli/v2/task_workflow_core.py`
     - CLI tests that assert exact script command strings in `tests/horadus_cli/v2/test_cli.py`
     - wrapper entrypoints:
       - `scripts/check_agent_task_eligibility.sh`
       - `scripts/task_context_pack.sh`
       - `scripts/finish_task_pr.sh`
       - `scripts/check_pr_task_scope.sh`
       - `scripts/run_unit_coverage_gate.sh`
       - `scripts/test_integration_docker.sh`
   - identify which of those callers must remain zero-install/bootstrap safe, especially CI workflow guards that run before dependency installation
   - identify which finish-path callers depend on exact review-gate script paths or direct script execution, especially:
     - `src/horadus_cli/v2/task_workflow_core.py`
     - `tests/horadus_cli/v2/test_cli.py`
     - `tests/unit/scripts/test_check_pr_review_gate.py`
   - identify which callers depend on file-path loading plus module-global overrides, especially:
     - `scripts/check_pr_closure_state.py` loading `src/horadus_cli/v2/task_repo.py` directly
     - tests that monkeypatch `repo_root` on module objects rather than through an imported interface
   - decide the workflow↔CLI result contract explicitly before moving code:
     - either move `result.py` to neutral ownership outside CLI
     - or make workflow return plain data/domain results and keep CLI-only `CommandResult` adaptation in CLI modules
     - do not leave workflow importing CLI-owned result types after extraction
   - inventory every current repo-root caller and override seam, including:
     - `src/horadus_cli/v2/task_repo.py`
     - `src/horadus_cli/v2/task_workflow_core.py`
     - `scripts/check_pr_closure_state.py`
     - `tests/horadus_cli/v2/test_task_workflow_v2.py`
   - decide explicitly how the existing versioned-shell compatibility tests are handled:
     - default: they remain authoritative for this task
     - therefore `src.horadus_cli.*` stays the public Python compatibility surface
     - extracted workflow code must sit behind that surface via shims/adapters instead of replacing it outright
   - classify each module as app/runtime, workflow, CLI, or script wrapper
   - choose the enduring CLI owner for parser registration/helpers explicitly:
     - `src/horadus_cli/*/task_commands.py` remains the owner of task parser wiring and shared leaf CLI options
     - workflow modules must not remain a second owner of `register_task_commands` or `add_leaf_cli_options`
   - choose the final tooling/workflow root and target module map
   - select a language-neutral home, for example:
     - `tools/horadus/`
     - `workflow/horadus/`
     - but not a Python-app-only root like `src/horadus_workflow/`
   - define the interim Python import strategy explicitly before moving code, for example:
     - `tools/horadus/python/horadus_workflow/` as the importable Python package root inside the language-neutral home
     - project/test config updated so CLI, scripts, and tests import that package directly during the Python phase
     - no direct app/runtime ownership fallback under `src/`
   - define the packaging/coverage transition explicitly before moving code:
     - `pyproject.toml` install metadata updated so the extracted Python workflow package is included in the built/installable distribution
     - the `horadus` script entrypoint remains stable while importing through the existing public CLI shell
     - coverage configuration and the unit-coverage gate continue to measure extracted Python workflow code at 100%
   - define the full enforced-gate transition explicitly before moving code:
     - lint and format targets include the extracted workflow home
     - mypy/type-check targets include the extracted workflow home
     - security scan scope includes the extracted workflow home
     - build/install config includes the extracted workflow home
     - canonical local gate and CI jobs keep enforcing those targets after extraction
   - define the zero-install bootstrap transition explicitly before moving code:
     - workflow guard scripts that run before dependency install must keep a raw-checkout import path
     - those entrypoints may load workflow code by file path or another dependency-light mechanism
     - they must not start requiring `uv sync`, package install, or third-party runtime dependencies just to execute
     - explicitly cover `scripts/check_pr_closure_state.py` and `scripts/check_docs_freshness.py`
   - define the repo-root transition explicitly before moving code:
     - introduce one stable repo-root resolver contract in the workflow home
     - support explicit override seams for tests and bootstrap callers
     - use repository-marker discovery or another location-stable rule for default resolution
     - do not rely on `Path(__file__).resolve().parents[N]`
     - explicitly preserve bootstrap callers that currently assume raw-checkout repo-root behavior, especially `scripts/check_pr_closure_state.py`
     - explicitly preserve module-global override behavior where current bootstrap callers patch `repo_root` on the loaded module object
   - choose the target test ownership map before moving code:
     - `tests/workflow/` for workflow package behavior and boundary tests
     - `tests/horadus_cli/` for parser, routing, rendering, and shell behavior
     - `tests/unit/core/` for actual app-core/domain logic only
     - `tests/unit/scripts/` only for true script-wrapper entrypoints if those wrappers remain

2. Implement
   - create the tooling/workflow home, tentatively `tools/horadus/`
   - create the interim Python implementation root inside it and wire imports/tests to that root first
   - move workflow ownership out of:
     - `src/horadus_cli/v2/task_repo.py`
     - `src/horadus_cli/v2/task_workflow_core.py`
     - `src/horadus_cli/v2/task_workflow_policy.py`
     - `src/core/docs_freshness.py`
     - `src/core/repo_workflow.py`
     - repo workflow scripts under `scripts/`
   - keep non-workflow operational CLI code out of scope unless a temporary import shim is required to avoid breaking the shell during extraction
   - preserve import compatibility during the move explicitly:
     - temporary compatibility shims are allowed at old Python module paths during the extraction
     - each shim must delegate immediately to the new workflow home
     - shims are transitional only and must not become new logic owners
     - remove or minimize shims before task close where safe, but do not break the CLI/scripts/tests mid-migration
     - simple import re-export shims are not sufficient for file-path-loaded modules whose callers patch module globals
     - where a bootstrap caller loads an old file path directly, preserve a real compatibility module at that path or change the caller in the same step
     - specifically, any compatibility module used by `scripts/check_pr_closure_state.py` must preserve the loaded-module `repo_root` override seam for `task_closure_state()`, not just re-export names from the new owner
   - preserve the current public Python CLI shell contract explicitly:
     - `src/horadus_cli/*` remains the public Python import surface during this task
     - the tooling/workflow home becomes the implementation owner behind that surface
     - do not turn this task into a public CLI module-layout rewrite
   - preserve parser-helper ownership explicitly:
     - keep `src/horadus_cli/*/task_commands.py` as the single CLI owner of task parser registration and shared leaf CLI options
     - allow other CLI modules such as triage commands to import those helpers from that one owner
     - remove duplicate parser-registration/helper copies from workflow-owned modules during the extraction
   - preserve versioned-shell compatibility tests as authoritative by default:
     - keep top-level `src.horadus_cli.*` wrappers importable/executable
     - allow those wrappers to become thin shims/adapters to the workflow home
     - do not rewrite `tests/horadus_cli/shell/test_cli_versioning.py` to bless a new public import shape in this task
     - if that shell contract ever needs to change, split it into a separate task
   - preserve literal wrapper/command compatibility where current CLI/tests require it:
     - keep script paths or compatibility wrappers stable where `task_workflow_core` or tests assert exact commands
     - if a literal command path must change, update the caller inventory and its regression tests in the same change
     - explicitly preserve the `./scripts/check_pr_review_gate.py` finish-path contract until a separate task changes it deliberately
   - preserve bootstrap-safe guard entrypoints explicitly:
     - scripts like `scripts/check_pr_closure_state.py` may need a dedicated dependency-light loading path
     - do not force those guards through the normal installed CLI/package path if that would require dependency installation
     - keep `scripts/check_docs_freshness.py` bootstrap-safe if it remains a direct script entrypoint during the migration
     - if a bootstrap guard patches module globals after loading a file path, preserve that behavior explicitly or replace it with one documented bootstrap-safe override seam in the same change
     - for `scripts/check_pr_closure_state.py`, either keep a compatibility module whose functions resolve `repo_root` through the loaded module object, or migrate the guard to a new explicit override seam in the same change
   - preserve repo-root compatibility explicitly:
     - move workflow-owned repo-root lookups behind one stable resolver contract
     - keep tests/bootstrap callers able to override that resolver intentionally
     - remove path-depth-based repo-root ownership logic from moved workflow modules
     - for file-path-loaded compatibility modules, keep override hooks resolving against the loaded module object until all such callers are migrated
     - do not treat `from new_module import *` as sufficient for old file-path compatibility when callers mutate module globals before invoking exported functions
   - break the current CLI-result-type coupling explicitly:
     - move shared result envelopes to neutral ownership, or
     - keep workflow return values CLI-agnostic and adapt them to `CommandResult` only in CLI modules
     - do not leave workflow modules importing `src/horadus_cli/*/result.py`
   - structure the new home so a later Go rewrite can reuse the same top-level ownership boundary, for example:
     - `tools/horadus/internal/workflow/`
     - `tools/horadus/internal/cli/`
     - `tools/horadus/cmd/horadus/`
     - while allowing an interim Python implementation if needed
   - move workflow-owned tests out of mixed locations, including:
     - `tests/unit/core/test_docs_freshness.py`
     - any workflow-heavy tests still living under `tests/horadus_cli/`
     - any script tests that are actually workflow behavior tests rather than wrapper tests
   - keep `scripts/` only for:
     - CI entrypoints
     - hook entrypoints
     - local wrapper commands that delegate immediately into workflow code
   - do not leave standalone workflow policy logic in `scripts/`
   - leave CLI modules owning only:
     - argument parsing
     - command registration
     - output rendering
     - exit-code mapping
   - leave scripts owning only CLI-free wrapper entrypoints

3. Validate
   - add import-boundary tests that enforce:
     - workflow imports only stdlib + workflow-local modules
     - CLI may import workflow
     - workflow may not import CLI
     - workflow may not import app/runtime packages
     - app/runtime packages may not import workflow
   - add test-ownership checks or explicit assertions that:
     - docs/task/PR workflow tests no longer live under app-core test paths by default
     - CLI tests do not become the primary owner of workflow policy behavior
     - script tests do not become the primary owner of workflow behavior; they only verify wrapper/entrypoint contracts
   - add at least one unaffected-caller regression for a shared helper moved out of core/CLI ownership
   - add at least one bootstrap-safe regression for a zero-install guard entrypoint
   - add at least one regression covering `scripts/check_docs_freshness.py` if it remains as a script wrapper
   - add or keep one regression proving parser registration/helpers have a single enduring owner and are not duplicated in workflow modules
   - keep regressions green for `scripts/check_pr_review_gate.py` and its direct script test surface
   - add at least one regression proving repo-root resolution still works after moving workflow owners deeper than the current `src/` layout
   - keep repo-root override tests green, or migrate them to the single stable resolver seam in the same change
   - add at least one regression for a file-path-loaded compatibility module whose caller overrides `repo_root` on the loaded module object
   - add at least one regression specifically covering the `check_pr_closure_state.py` pattern: load old module path, override `repo_root` on that module object, then call `task_closure_state()`
   - keep `tests/horadus_cli/shell/test_cli_versioning.py` green unless a separately approved task changes that compatibility contract
   - keep regressions green for exact command/wrapper callers currently asserted by:
     - `tests/horadus_cli/v2/test_cli.py`
     - `tests/unit/scripts/test_check_agent_task_eligibility.py`
     - `tests/unit/scripts/test_task_context_pack.py`
     - `tests/unit/scripts/test_finish_task_pr.py`
     - `tests/unit/scripts/test_run_unit_coverage_gate.py`
   - rerun CLI regression coverage for `horadus tasks ...` and `horadus triage ...`
   - rerun script coverage for PR/task/docs workflow guards
   - rerun workflow-home tests from their new dedicated test surface
   - rerun the full enforced repo gate surface against the new layout:
     - lint/format
     - type check
     - security scan
     - build/install
     - canonical local gate
     - CI workflow configuration
   - use staged validation during the migration:
     - before `tests/workflow/` exists, keep the current workflow-owned tests green in their existing locations
     - once `tests/workflow/` is created, move workflow-owned coverage there and make that path the canonical validation target
     - do not leave duplicated long-term ownership between old test paths and `tests/workflow/`

4. Ship (PR, checks, merge, main sync)
   - update required stable docs to reflect the new ownership model:
     - `docs/AGENT_RUNBOOK.md` for operator/developer entrypoints
     - `AGENTS.md` only if workflow/package boundary rules or required commands materially change
   - update `docs/ARCHITECTURE.md` or add a short ADR only if the final ownership layout is a durable architectural change rather than a temporary migration detail
   - keep migration mechanics, temporary shim details, and transient compatibility notes in the exec plan/PR notes rather than general docs
   - run required local gates
   - open PR, complete review/check flow, merge, and sync local `main`

## Decisions (Timestamped)

- 2026-03-11: Prefer one dedicated tooling/workflow home over scattered script-only utilities so workflow code stays importable, testable, and reviewable.
- 2026-03-11: Keep the external `horadus` CLI stable; CLI is an adapter layer, not the owner of workflow policy.
- 2026-03-11: Treat `src/core/docs_freshness.py` as workflow code, not app-core code, and move it accordingly.
- 2026-03-11: Avoid a Python-`src`-only target because CLI/workflow may later be reimplemented in Go without changing the repo ownership model.

## Risks / Foot-guns

- boundary blur can reappear after the move -> add import-boundary tests and document allowed dependency directions
- CLI behavior can drift during extraction -> preserve CLI regression coverage and keep rendering in CLI adapters only
- scripts can remain hidden second owners -> convert them into thin wrappers over shared workflow functions
- package naming churn can over-expand scope -> keep one tooling/workflow home only and avoid extra overlapping top-level categories
- wrapper scripts can silently retain real logic -> enforce that scripts are transport only and move behavior tests to workflow-owned suites
- the interim Python layout can become accidental permanent architecture -> document it as a bridge inside the tooling home, not the final language commitment
- compatibility shims can become permanent hidden owners -> allow them only as migration bridges and keep logic/test ownership moving to the workflow home
- simple re-export shims can fail bootstrap callers that patch module globals on file-path-loaded modules -> preserve real compatibility modules or migrate those callers atomically
- closure-guard compatibility can still break behind a seemingly importable shim -> preserve the loaded-module `repo_root` override seam or replace it atomically with a documented bootstrap-safe seam
- extracted code can fall out of install or coverage gates -> update build/entrypoint/coverage config as part of the same task, not as follow-up cleanup
- bootstrap guards can break before deps install -> preserve raw-checkout/system-Python execution for those entrypoints throughout the migration
- extracted workflow code can fall out of lint/typecheck/security/local-gate/CI scope -> update every enforced gate target in the same task, not incrementally later
- versioned-shell compatibility can accidentally turn into a public CLI layout rewrite -> keep the current shell tests authoritative and hide the extraction behind shims/adapters
- literal script-path compatibility can be broken accidentally -> inventory and preserve exact command callers until a separate contract-change task updates them deliberately
- path-depth-based repo-root discovery can break immediately after moving modules deeper -> replace it with one stable resolver contract before relying on the new tooling home
- workflow can stay unintentionally coupled to CLI-owned result types -> choose and enforce one CLI-agnostic result contract during the extraction
- finish-path review-gate compatibility can break silently -> preserve `check_pr_review_gate.py` exact-path callers and its direct tests during the extraction
- parser-helper ownership can stay duplicated across CLI and workflow layers -> keep one explicit CLI owner and remove workflow-side copies during the extraction

## Validation Commands

- `uv run --no-sync pytest tests/unit/core/test_docs_freshness.py -q` (until migrated to `tests/workflow/`)
- `uv run --no-sync pytest tests/horadus_cli -q`
- `uv run --no-sync pytest tests/workflow -q`
- `uv run --no-sync pytest tests/unit/scripts -q`
- `python3 ./scripts/check_pr_closure_state.py --task-id TASK-303 --repo-root .`
- `uv run --no-sync ruff format --check src/ tests/` (or updated equivalent once workflow home is included)
- `uv run --no-sync ruff check src/ tests/` (or updated equivalent once workflow home is included)
- `uv run --no-sync mypy src/` (or updated equivalent once workflow home is included)
- `uv run --no-sync pre-commit run --all-files`
- `uv run --no-sync pre-commit run --hook-stage pre-push --all-files`

## Notes / Links

- Spec:
  - `tasks/BACKLOG.md`
- Relevant modules:
  - `src/horadus_cli/`
  - `src/horadus_cli/v2/task_repo.py`
  - `src/horadus_cli/v2/task_workflow_core.py`
  - `src/horadus_cli/v2/task_commands.py`
  - `src/horadus_cli/v2/triage_commands.py`
  - `src/horadus_cli/v2/result.py`
  - `scripts/`
  - `scripts/check_pr_review_gate.py`
  - `scripts/check_docs_freshness.py`
  - `scripts/check_pr_closure_state.py`
  - `src/core/docs_freshness.py`
  - `src/core/repo_workflow.py`
  - `pyproject.toml`
  - `.github/workflows/ci.yml`
  - `scripts/run_unit_coverage_gate.sh`
  - `docs/AGENT_RUNBOOK.md`
  - `AGENTS.md`
  - `docs/ARCHITECTURE.md`
  - `tests/horadus_cli/`
  - `tests/horadus_cli/v2/test_task_workflow_v2.py`
  - `tests/unit/scripts/`
- Initial extraction set:
  - task lifecycle / ledger / context-pack / finish workflow
  - triage/intake workflow
  - PR/review/closure workflow guards
  - docs-freshness workflow logic
  - workflow-policy helpers currently in `src/core/repo_workflow.py`
- Known caller inventory to preserve:
  - `scripts/check_pr_closure_state.py`
  - `scripts/check_pr_review_gate.py`
  - `scripts/check_docs_freshness.py`
  - `tests/horadus_cli/shell/test_cli_versioning.py`
  - `tests/unit/core/test_repo_workflow.py`
  - `tests/unit/core/test_docs_freshness.py`
  - `tests/unit/scripts/test_check_pr_review_gate.py`
  - task/triage CLI callers inside `src/horadus_cli/`
  - CI workflow-guard entrypoints that execute before dependency install
  - local-gate/pr-finish command builders in `src/horadus_cli/v2/task_workflow_core.py`
  - exact command assertions in `tests/horadus_cli/v2/test_cli.py`
  - wrapper entrypoints:
    - `scripts/check_agent_task_eligibility.sh`
    - `scripts/task_context_pack.sh`
    - `scripts/finish_task_pr.sh`
    - `scripts/check_pr_task_scope.sh`
    - `scripts/run_unit_coverage_gate.sh`
    - `scripts/test_integration_docker.sh`
- Workflow↔CLI result contract for this task:
  - workflow must not keep importing CLI-owned result types
  - either move shared result envelopes to neutral ownership or keep workflow return values CLI-agnostic and adapt them in CLI modules only
- Parser-helper ownership for this task:
  - `src/horadus_cli/*/task_commands.py` remains the single CLI owner of task parser wiring and shared leaf CLI options
  - workflow modules must not remain a second owner of `register_task_commands` or `add_leaf_cli_options`
- Repo-root contract for this task:
  - workflow code must not rely on module-path depth for locating the repository root
  - use one stable resolver contract that supports both normal runtime and explicit test/bootstrap overrides
  - preserve current file-path-loaded module override behavior until those callers are migrated to the stable resolver seam
- Authoritative Python compatibility surface for this task:
  - `src/horadus_cli/*` remains the public shell/wrapper layer
  - `tests/horadus_cli/shell/test_cli_versioning.py` remains authoritative unless a separate task explicitly changes that contract
- Target tooling layout:
  - `src/`
    - app/runtime only
  - `tools/horadus/` or equivalent language-neutral home
    - workflow ownership
    - CLI adapter implementation
    - future Go rewrite target if adopted
    - interim Python implementation root during the current phase
  - `scripts/`
    - thin entrypoints only
    - no long-term ownership of workflow policy/ledger/docs logic
- Target test layout:
  - `tests/workflow/`
    - workflow policy/ledger/docs-freshness/review-gate/task-lifecycle behavior
  - `tests/horadus_cli/`
    - CLI parser wiring, shell routing, rendering, exit-code mapping
  - `tests/unit/core/`
    - app-core/domain logic only; no repo workflow ownership
  - `tests/unit/scripts/`
    - wrapper entrypoints only if standalone scripts still exist after extraction
- Boundary contract:
  - workflow may not import CLI or app/runtime packages
  - CLI may import workflow through documented APIs only
  - scripts may import workflow directly as thin wrappers
  - the ownership boundary should remain stable even if CLI/workflow implementation language changes later
  - `src/horadus_cli/*` stays the public Python CLI compatibility surface during this task
  - bootstrap guard scripts may use a separate dependency-light loading path and are not required to go through the installed CLI path
- Canonical example: `tasks/specs/275-finish-review-gate-timeout.md`
