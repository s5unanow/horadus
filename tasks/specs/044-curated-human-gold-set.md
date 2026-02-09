# TASK-044: Curated Human-Verified Gold Dataset [REQUIRES_HUMAN]

## Objective

Build a high-trust evaluation gold set from real-world items with manual human verification.

## Why This Is Human-Gated

- The benchmark must reflect analyst-grade judgment, not only synthetic/LLM-seeded labels.
- Final label acceptance requires a human reviewer for credibility and auditability.

## Scope

- Source representative real items across tracked trends and noise/irrelevant cases.
- Apply Tier-1 and Tier-2 labels using a consistent rubric.
- Require explicit human review/sign-off for every included row.

## Output

- Updated `ai/eval/gold_set.jsonl` with `label_verification="human_verified"` rows.
- Optional supporting draft set (silver) may remain with non-human labels.
- Reviewer notes in sprint/task docs showing completion evidence.

## Acceptance Checklist

- [ ] At least 200 representative real items selected
- [ ] Every row manually reviewed by a human
- [ ] Label consistency pass completed (trend/signal/direction/severity/confidence)
- [ ] Sampling includes hard negatives and ambiguous edge cases
- [ ] Human reviewer sign-off captured in `tasks/CURRENT_SPRINT.md`
