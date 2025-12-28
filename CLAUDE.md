# Agent Instructions (Claude / Codex / Gemini)

This file is intentionally tool-agnostic. If your agent supports `AGENTS.md`, read `AGENTS.md` first; otherwise this file contains the full project orientation.

Important: this is a **hobby/personal** system, but it should be treated as **mature and production-shaped**. Assume **≤ 20 trends**: keep scope small while still adhering to **enterprise best practices** where reasonable (tests, migrations, type safety, structured logging, safe defaults, and cost controls). Avoid premature over-engineering.

# Geopolitical Intelligence Platform

## Project Overview

Building a headless backend that:
1. Collects news from multiple sources (RSS, GDELT, Telegram)
2. Classifies them via LLM with smart filtering
3. Clusters articles into events (many articles → one event)
4. Tracks geopolitical trend probabilities using log-odds
5. Generates periodic reports with retrospective analysis

**Key Principle**: LLM extracts structured signals; deterministic code computes probability deltas.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12 |
| API | FastAPI + Pydantic |
| Database | PostgreSQL + TimescaleDB + pgvector |
| Queue | Redis + Celery |
| LLM | OpenAI API (gpt-4.1-nano for filtering, gpt-4o-mini for classification) |
| Scraping | feedparser, Trafilatura, Telethon |

## Project Navigation

```
geopolitical-intel/
├── AGENTS.md              # Tool-agnostic agent instructions (start here)
├── CLAUDE.md              ← You are here (agent instructions)
├── PROJECT_STATUS.md      ← Current progress, what's done/next
├── tasks/
│   ├── BACKLOG.md         ← All planned tasks
│   ├── CURRENT_SPRINT.md  ← Active tasks (check this first)
│   └── specs/             ← Detailed task specifications
├── docs/
│   ├── ARCHITECTURE.md    ← System design (READ THIS)
│   ├── DATA_MODEL.md      ← Database schema
│   ├── GLOSSARY.md        ← Domain terminology
│   └── adr/               ← Architecture Decision Records
├── src/                   ← Source code
├── tests/                 ← Test files
└── config/                ← Configuration files
```

## Before Starting Any Task

1. **Read the task spec** in `tasks/specs/` if it exists
2. **Check architecture** in `docs/ARCHITECTURE.md` for system context
3. **Check data model** in `docs/DATA_MODEL.md` for schema
4. **Run existing tests**: `pytest tests/ -v`

## After Completing Any Task

1. **Update** `tasks/CURRENT_SPRINT.md` (mark task as DONE)
2. **Move completed tasks** to `tasks/COMPLETED.md`
3. **Update** `PROJECT_STATUS.md` if milestone reached
4. **Add ADR** to `docs/adr/` if significant decision was made
5. **Run tests** to verify nothing broke: `pytest tests/ -v`

## Code Conventions

### General
- **Type hints required** on all functions
- **Pydantic models** for all data structures
- **Async everywhere** (FastAPI, asyncpg, httpx)
- **Docstrings** on public classes and functions

### File Organization
- Database models: `src/storage/models.py`
- Database operations: `src/storage/repositories.py`
- API routes: `src/api/routes/*.py`
- Core domain logic: `src/core/*.py`
- Celery tasks: `src/workers/tasks.py`
- LLM interactions: `src/processing/llm_classifier.py`

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

### Testing
- Tests mirror `src/` structure in `tests/unit/`
- Use pytest fixtures for common setup
- Integration tests require running database

## Git Conventions

### Branch Naming

```
main              ← Production-ready code
develop           ← Integration branch (optional for solo dev)
feature/TASK-XXX-short-description
fix/TASK-XXX-short-description
refactor/short-description
docs/short-description
```

**Examples:**
```
feature/TASK-006-rss-collector
feature/TASK-028-risk-levels
fix/TASK-017-decay-calculation
refactor/trend-engine-cleanup
docs/api-documentation
```

### Commit Message Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**Types:**
| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change that neither fixes nor adds |
| `docs` | Documentation only |
| `test` | Adding/updating tests |
| `chore` | Maintenance (deps, config, etc.) |
| `perf` | Performance improvement |

**Scope** (optional): Module affected (`api`, `core`, `storage`, `ingestion`, `processing`, `workers`)

**Examples:**
```
feat(core): implement risk level calculation

Adds RiskLevel enum and get_risk_level() function.
Maps probability to Low/Guarded/Elevated/High/Severe.

Closes TASK-028
```

```
fix(storage): correct decay half-life calculation

The decay was using days instead of hours for the
half-life calculation, causing probabilities to
decay too slowly.

Fixes TASK-017
```

```
docs: add API endpoint documentation
```

```
chore: update anthropic SDK to 0.18.0
```

```
test(core): add trend engine edge case tests
```

### Commit Best Practices

1. **Atomic commits**: One logical change per commit
2. **Reference tasks**: Include `TASK-XXX` in body/footer
3. **Present tense**: "Add feature" not "Added feature"
4. **No period** at end of subject line
5. **50/72 rule**: Subject ≤50 chars, body wrapped at 72

### When to Commit

- After completing a logical unit of work
- Before switching to a different task
- After all tests pass
- After making the code work (commit working state)

### Pull Request / Merge Strategy

For solo development:
```bash
# Work on feature branch
git checkout -b feature/TASK-006-rss-collector

# Make commits...

# When done, merge to main
git checkout main
git merge feature/TASK-006-rss-collector
git push origin main

# Delete feature branch
git branch -d feature/TASK-006-rss-collector
```

### .gitignore Essentials

Already configured, but verify these are ignored:
```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/
```

## Common Commands

```bash
# Start services (database, redis)
make docker-up

# Run database migrations
make db-upgrade

# Start API server (development)
make run

# Start Celery worker
make run-worker

# Start Celery beat (scheduler)
make run-beat

# Run all tests
make test

# Run specific test file
pytest tests/unit/core/test_trend_engine.py -v

# Run with coverage
make test-cov

# Code quality check (lint + type + format)
make check
```

## Key Architectural Decisions

### 1. Log-Odds for Probability (ADR-003)
We track trend probabilities using log-odds, not raw percentages.
- Mathematically sound (always valid 0-1 range)
- Evidence is additive
- See `docs/adr/003-probability-model.md`

### 2. Events > Articles (ADR-004)
Multiple articles about the same story become ONE event.
- Reduces noise
- Corroboration count matters
- See `docs/adr/004-event-clustering.md`

### 3. Two-Tier LLM Processing (ADR-005)
- **Tier 1 (Haiku)**: Quick relevance scoring (cheap, fast)
- **Tier 2 (Sonnet)**: Full classification + extraction (expensive, thorough)
- Only ~20% of items reach Tier 2

### 4. Deterministic Scoring (ADR-006)
LLM outputs structured signals. Code computes deltas.
- Explainable: every probability change has a paper trail
- Debuggable: no "the AI said so" black boxes
- Consistent: same inputs → same outputs

## Environment Variables

Required in `.env`:
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/geoint
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...

# Optional
GDELT_API_KEY=...
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```

## Troubleshooting

### Database connection issues
```bash
# Check if PostgreSQL is running
docker-compose ps
# Check logs
docker-compose logs postgres
```

### Celery tasks not running
```bash
# Check if Redis is running
docker-compose ps
# Check Celery worker logs
celery -A src.workers.celery_app worker --loglevel=debug
```

### Import errors
```bash
# Make sure you're in the project root
# Make sure virtual environment is activated
source .venv/bin/activate
# Install in development mode
pip install -e .
```

## Quick Reference: Domain Concepts

| Term | Definition |
|------|------------|
| **RawItem** | Single article/post from a source |
| **Event** | Cluster of RawItems about the same story |
| **Trend** | Hypothesis being tracked (e.g., "EU-Russia conflict") |
| **Signal** | Extracted fact that affects a trend |
| **Evidence** | A signal's contribution to a trend's probability |
| **Log-odds** | ln(p / (1-p)), our internal probability representation |

## Getting Oriented

If starting fresh or resuming work:

```
1. Read PROJECT_STATUS.md     → Understand current state
2. Read CURRENT_SPRINT.md     → See active tasks
3. Pick a task or ask         → "What should I work on?"
4. Read task spec if exists   → tasks/specs/XXX-task-name.md
5. Implement                  → Write code, tests
6. Verify                     → Run tests, check types
7. Update tracking            → Mark done, update status
```
