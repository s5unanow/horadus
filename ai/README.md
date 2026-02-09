# AI Assets

This folder stores **LLM-related artifacts** that benefit from versioning and review, separate from application code.

Goals:
- Keep prompts editable without changing Python code
- Make evaluation repeatable (human-verified gold set + benchmark results)
- Keep the project “production-shaped” without over-engineering

## Structure

- `ai/prompts/` — prompt templates for Tier 1 / Tier 2
- `ai/eval/` — evaluation datasets and benchmark outputs (see `TASK-041`)

## Conventions

- Treat prompts as production artifacts: review changes like code.
- Keep evaluation data **non-sensitive** (no private info, no real API keys).
