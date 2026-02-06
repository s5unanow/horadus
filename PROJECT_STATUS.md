# Project Status

**Last Updated**: 2026-02-06
**Current Phase**: Phase 1 - Data Ingestion (starting)

## Progress Overview

```
Phase 0: Setup & Foundation  [████████████████████] 100%  ✅ COMPLETE
Phase 1: Data Ingestion      [░░░░░░░░░░░░░░░░░░░░]   0%  ← WE ARE HERE
Phase 2: Processing Layer    [░░░░░░░░░░░░░░░░░░░░]   0%
Phase 3: Trend Engine        [░░░░░░░░░░░░░░░░░░░░]   0%
Phase 4: Reporting           [░░░░░░░░░░░░░░░░░░░░]   0%
Phase 5: Polish & Deploy     [░░░░░░░░░░░░░░░░░░░░]   0%
Phase 6: Calibration (NEW)   [░░░░░░░░░░░░░░░░░░░░]   0%
```

## What's Working

- [x] Project structure created (src/, tests/, docs/, config/)
- [x] Documentation framework (ARCHITECTURE, DATA_MODEL, GLOSSARY)
- [x] Task tracking system (BACKLOG, CURRENT_SPRINT, specs)
- [x] pyproject.toml with all dependencies
- [x] docker-compose.yml (PostgreSQL + TimescaleDB + Redis)
- [x] Database models (all entities including expert recommendations)
- [x] Alembic configuration
- [x] Initial Alembic migration created (schema + extensions + hypertable)
- [x] FastAPI skeleton with route stubs
- [x] Core config module (Pydantic Settings)
- [x] Trend engine core (log-odds math, evidence calculation)
- [x] EU-Russia trend config with enhanced schema
- [x] Makefile for common workflows
- [x] RSS collector foundation (config load, fetch/parse, extraction, dedup, persistence)

## In Progress

- [ ] TASK-006: RSS collector (Phase 1 start)

## Blocked

- Nothing currently blocked

## Next Up (Priority Order)

1. Implement Phase 1 RSS ingestion pipeline (TASK-006)
2. Add source fetch scheduling and retries
3. Add ingestion observability (structured logs + metrics)
4. Add ingestion integration tests (no external network)
5. Prepare GDELT collector baseline (TASK-007)

## Expert Feedback Integration ✅

Based on expert review, added 9 new tasks:

| Task | Description | Priority |
|------|-------------|----------|
| TASK-028 | Risk levels + probability bands | P1 |
| TASK-029 | Enhanced trend definitions | P2 |
| TASK-030 | Event lifecycle tracking | P1 |
| TASK-031 | Source tier and reporting type | P2 |
| TASK-032 | Trend outcomes for calibration | P1 |
| TASK-033 | Contradiction detection | P2 |
| TASK-034 | Human feedback API | P2 |
| TASK-035 | Calibration dashboard | P2 |
| TASK-036 | Cost protection & budget limits | P1 |

### Key Additions
- **Risk levels**: Low / Guarded / Elevated / High / Severe
- **Event lifecycle**: emerging → confirmed → fading → archived
- **Source tiers**: primary / wire / major / regional / aggregator
- **Calibration**: Brier scores, outcome tracking
- **Cost protection**: Kill switch for API spend
- **Trend config**: disqualifiers, falsification criteria

## Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| M1: Basic API + DB running | Week 1 | ✅ Complete |
| M2: RSS ingestion working | Week 2 | 🔲 Not Started |
| M3: GDELT integration | Week 3 | 🔲 Not Started |
| M4: LLM classification pipeline | Week 4 | 🔲 Not Started |
| M5: Trend engine operational | Week 5 | 🔲 Not Started |
| M6: Weekly reports generating | Week 6 | 🔲 Not Started |
| M7: Telegram integration | Week 7 | 🔲 Not Started |
| M8: Full system operational | Week 8 | 🔲 Not Started |

## Known Issues

- None yet

## Architecture Validated ✅

Expert confirmed core design:
- ✅ Events as core unit (not articles)
- ✅ Log-odds for probability tracking
- ✅ LLM extracts signals; code computes deltas
- ✅ Two-tier LLM processing (Tier 1 → Tier 2)
- ✅ Evidence ledger with full provenance

## Recent Decisions

- Project bootstrapped with agent-friendly structure
- Using log-odds for probability tracking (ADR-003)
- Two-tier LLM processing (Tier 1 → Tier 2) (ADR-005)
- Risk levels instead of single probability numbers (expert feedback)
- Event lifecycle to reduce noise (expert feedback)
- Calibration infrastructure for long-term accuracy (expert feedback)

## Technical Debt

- None yet (fresh project)

## Notes

- MVP path: Ingest → Cluster → Score → Report (Phases 0-4)
- Calibration meaningful after 2+ months of data
- Knowledge graph deferred (PostgreSQL sufficient for MVP)
- Remember to update this file when completing milestones
