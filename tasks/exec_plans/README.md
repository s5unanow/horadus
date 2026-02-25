# Execution Plans

Execution plans are "living docs" used for complex tasks to keep agent/human
context small and to prevent drift during multi-hour work.

Use when a task is expected to:
- take >2 hours, or
- touch >5 files, or
- involve migrations, LLM/pipeline changes, probability math, or ops guardrails.

Convention:
- One file per task: `tasks/exec_plans/TASK-XXX.md`
- Start from: `tasks/exec_plans/TEMPLATE.md`
