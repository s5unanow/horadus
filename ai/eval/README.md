# Evaluation

This folder is the home for model/provider evaluation artifacts (`TASK-039`).

Recommended layout:

- `ai/eval/gold_set.jsonl` — labeled items (inputs + expected structured outputs)
- `ai/eval/results/` — benchmark outputs (timestamped)

Notes:
- Keep gold data small, curated, and representative.
- Avoid storing sensitive content.
