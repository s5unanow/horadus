# Responses API Migration Plan

**Last Verified**: 2026-02-16

## Migration Inventory

Current OpenAI chat-completions call sites:

- `src/processing/tier1_classifier.py` (Tier-1 classification, strict schema)
- `src/processing/tier2_classifier.py` (Tier-2 extraction, strict schema)
- `src/core/report_generator.py` (weekly/monthly narratives)
- `src/core/retrospective_analyzer.py` (retrospective narratives)
- `src/eval/benchmark.py` (offline evaluation benchmark)

Non-chat OpenAI call sites:

- `src/processing/embedding_service.py` (embeddings API)

## Unified Invocation Policy

`src/processing/llm_policy.py` is now the shared invocation policy layer used by
Tier-1, Tier-2, reports, and retrospectives. It centralizes:

- budget checks + usage accounting,
- retry/failover execution and strict-schema fallback,
- payload safety/truncation hooks,
- provider-neutral error handling through `LLMInvocationErrorCode`,
- model pricing estimation via `src/processing/llm_pricing.py`.

This removes duplicated invocation logic from classifier and narrative paths and
keeps per-stage model/provider selection at call sites.

## Adapter Layer

`src/processing/llm_invocation_adapter.py` is the shared invocation adapter used by
`LLMChatFailoverInvoker` routes. It supports:

- `chat_completions` mode (default)
- `responses` mode (pilot)

The adapter normalizes responses to the existing `choices[0].message.content` +
`usage.prompt_tokens/completion_tokens` shape to keep downstream code/parsing
unchanged.

## Pilot Migration (Implemented)

Pilot path: `src/core/report_generator.py`

- `LLM_REPORT_API_MODE` (`chat_completions` default, `responses` pilot) is routed
  through the unified policy + adapter path.
- Report and retrospective generation now use the same shared invocation policy
  as Tier-1/Tier-2 (budget, retry/failover, safety, usage/cost accounting).

## Risks

- Provider compatibility differences for Responses API fields and token accounting.
- Structured output support parity differs by model/provider.
- Mixed-mode operation can complicate incident triage if not logged clearly.

## Rollback

Immediate rollback for pilot:

1. Set `LLM_REPORT_API_MODE=chat_completions`.
2. Redeploy workers/API.
3. Confirm report generation returns to baseline path.

No schema migration is required.

## Remaining Migration Work

Runtime call sites (Tier-1/Tier-2/report/retrospective) now use shared policy
and adapter plumbing. Remaining migration work is concentrated in offline eval
paths and observability refinements.

## Follow-Up Checklist

- [ ] Add explicit Responses-mode telemetry tags to report pipeline metrics/logs.
- [ ] Evaluate Responses-mode parity in offline eval harness.
- [ ] Design/validate structured-output strategy for Responses API before Tier-1/2 migration.
- [ ] Migrate Tier-1/Tier-2 once strict structured parity and failure semantics are proven.
