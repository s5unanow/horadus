# Horadus Geopolitical Intelligence Platform

A headless backend for collecting, classifying, and analyzing news to track geopolitical trend probabilities.

## Repo Navigation

- Canonical workflow policy: `AGENTS.md`
- Command index: `docs/AGENT_RUNBOOK.md`
- Active task ledgers: `tasks/CURRENT_SPRINT.md`, `tasks/BACKLOG.md`, `tasks/COMPLETED.md`
- System design and schema: `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`
- Runtime truth for implementation questions: `src/`, `alembic/`, `tests/`

## Features

- **Multi-source ingestion**: RSS feeds, GDELT, Telegram channels
- **Smart filtering**: Two-tier LLM classification (cheap filter → expensive analysis)
- **Event clustering**: Groups duplicate news into single events
- **Event lifecycle tracking**: Emerging → confirmed → fading → archived
- **Trend tracking**: Bayesian-inspired probability updates using log-odds
- **Risk presentation**: Risk levels + probability bands + confidence ratings
- **Calibration visibility**: Reliability curve + Brier score dashboard
- **Automated reports**: Weekly/monthly trend analysis with retrospectives
- **Headless API**: REST endpoints for any frontend (web/mobile)

## Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- OpenAI API key

### Setup

```bash
# Clone and enter project
git clone <repo-url>
cd horadus

# Copy environment template
cp .env.example .env
# Edit .env with your API keys

# Create virtual environment (preferred: uv)
uv venv --python 3.12 .venv

# Full setup (installs deps, starts infra, runs migrations)
make setup

# Seed initial trends
python3 scripts/seed_trends.py

# Start API server
make run
```

Workflow/setup helpers:
- Use `docs/AGENT_RUNBOOK.md` for the current command index.
- Copy `.env.example` to `.env`; LLM provider selection lives in `docs/adr/002-llm-provider.md`.
- Typical local values include `DATABASE_URL`, `REDIS_URL`, and `OPENAI_API_KEY`.

### Start Workers

```bash
# In separate terminals:

# Celery worker (processes tasks)
make run-worker

# Celery beat (schedules periodic tasks)
make run-beat
```

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Sources   │     │  Processing │     │   Storage   │
│             │     │             │     │             │
│ • RSS       │────▶│ • Filter    │────▶│ • Events    │
│ • GDELT     │     │ • Classify  │     │ • Trends    │
│ • Telegram  │     │ • Cluster   │     │ • Evidence  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌─────────────┐             │
                    │   Reports   │◀────────────┘
                    │             │
                    │ • Weekly    │
                    │ • Monthly   │
                    │ • Retro     │
                    └─────────────┘
```

## API Documentation

Interactive OpenAPI docs are hosted by FastAPI:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

Detailed endpoint reference and curl examples:
- `docs/API.md`
- Deployment runbook:
  - `docs/DEPLOYMENT.md`
- Release runbook:
  - `docs/RELEASING.md`
- Environment variable reference:
  - `docs/ENVIRONMENT.md`
- Managed secret backend references:
  - `docs/SECRETS_BACKENDS.md`
- Prompt/model evaluation policy:
  - `docs/PROMPT_EVAL_POLICY.md`
- Evaluation workflow details:
  - `ai/eval/README.md`

Promotion quick path (dev -> staging -> prod):

```bash
make release-gate RELEASE_GATE_DATABASE_URL="<staging-db-url>"
```

Authentication header:
- `X-API-Key: <key>`
- Key-management admin header:
  - `X-Admin-API-Key: <key>`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/api/v1/trends` | List all trends with current probabilities |
| GET | `/api/v1/trends/{id}` | Get trend details |
| GET | `/api/v1/trends/{id}/history` | Get probability time series |
| GET | `/api/v1/trends/{id}/evidence` | Get events affecting trend |
| GET | `/api/v1/trends/{id}/retrospective` | Retrospective analysis |
| POST | `/api/v1/trends/{id}/outcomes` | Record resolved outcome for calibration |
| GET | `/api/v1/trends/{id}/calibration` | Get trend calibration report |
| GET | `/api/v1/events` | List recent events |
| GET | `/api/v1/events/{id}` | Get event details |
| GET | `/api/v1/reports` | List generated reports |
| GET | `/api/v1/reports/coverage` | Get recent source coverage health |
| GET | `/api/v1/reports/{id}` | Get report details |
| GET | `/api/v1/reports/calibration` | Calibration dashboard + trend movement visibility |
| GET | `/api/v1/auth/keys` | List API keys (admin) |
| POST | `/api/v1/auth/keys` | Create API key (admin) |
| POST | `/api/v1/auth/keys/{id}/rotate` | Rotate API key (admin) |
| DELETE | `/api/v1/auth/keys/{id}` | Revoke API key (admin) |

## CLI

Quick trend visibility from the terminal:

```bash
uv run horadus trends status
```

Export static calibration dashboard artifacts (JSON + HTML) for ops hosting:

```bash
uv run horadus dashboard export --output-dir artifacts/dashboard
```

Generate the daily grouped Horadus workflow friction summary:

```bash
uv run --no-sync horadus tasks summarize-friction --date YYYY-MM-DD
```

This writes `artifacts/agent/horadus-cli-feedback/daily/YYYY-MM-DD.md`. Review
the report before proposing any backlog follow-up; backlog task creation remains
human-gated.

Run the benchmark on the default baseline config set:

```bash
uv run --no-sync horadus eval benchmark
```

Use explicit `--config` flags to include optional GPT-5 candidate configs:

```bash
uv run --no-sync horadus eval benchmark \
  --config baseline \
  --config tier1-gpt5-nano-minimal \
  --config tier2-gpt5-mini-low
```

## Configuration

### Defining Trends

Trends are defined in `config/trends/`. Example:

```yaml
# config/trends/eu-russia.yaml
id: "eu-russia-conflict"
name: "EU-Russia Military Conflict"
description: "Probability of direct military confrontation between EU/NATO and Russia"

baseline_probability: 0.08

indicators:
  military_movement:
    weight: 0.04
    direction: escalatory
    type: leading
    keywords: ["troops", "deployment", "mobilization", "exercises", "nato"]

  sanctions:
    weight: 0.02
    direction: escalatory
    keywords: ["sanctions", "embargo", "restrictions", "freeze assets"]

  diplomatic_talks:
    weight: 0.03
    direction: de_escalatory
    type: leading
    keywords: ["talks", "negotiation", "summit", "agreement", "ceasefire"]

disqualifiers:
  - signal: peace_treaty_signed
    effect: reset_to_baseline
    description: "Formal ratified peace agreement"

falsification_criteria:
  decrease_confidence:
    - "Sustained de-escalation without incidents"
  increase_confidence:
    - "Direct military engagement between parties"

decay_half_life_days: 30
```

### Adding Sources

Sources are configured in `config/sources/`. Example:

```yaml
# config/sources/rss_feeds.yaml
feeds:
  - name: "Reuters World"
    url: "https://feeds.reuters.com/Reuters/worldNews"
    credibility: 0.95
    check_interval_minutes: 30

  - name: "BBC World"
    url: "http://feeds.bbci.co.uk/news/world/rss.xml"
    credibility: 0.90
    check_interval_minutes: 30
```

## Development

The project uses a `Makefile` to simplify common tasks. Run `make help` to see all available commands.

Fast local development commands:

```bash
make agent-check
uv run --no-sync horadus tasks local-gate --full
```

Repo workflow guidance:

- `AGENTS.md`: canonical workflow policy and completion rules
- `docs/AGENT_RUNBOOK.md`: short command index for day-to-day operator work
- `ops/skills/horadus-cli/`: thin agent-oriented CLI helper

If you are doing repo workflow work, start from `AGENTS.md` and use the
runbook/skill as quick references instead of separate policy sources.

## Production Deployment

Use the production Compose stack and container definitions:

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml --profile ops run --rm migrate
docker compose -f docker-compose.prod.yml up -d api worker beat postgres redis
```

See `docs/DEPLOYMENT.md` for the full deployment workflow and operational notes.

Backup operations:

```bash
make backup-db
make verify-backups
```

### Running Tests

```bash
# All tests
make test

# Unit coverage gate used by the workflow
make test-unit-cov

# Full test suite with coverage
make test-cov
```

### Code Quality

```bash
# Run formatter, linter, and type checker
make check
```

### Database Migrations

```bash
# Create new migration
make db-migrate msg="description"

# Apply migrations
make db-upgrade

# Rollback one step
make db-downgrade
```

## Documentation Freshness

Owner: release driver for each merged change.

Update timing:
- In the same PR whenever behavior, commands, or env vars change.
- During each tagged release using `docs/RELEASING.md` checklist.

Minimum docs to review per release:
- `README.md`
- `docs/DEPLOYMENT.md`
- `docs/ENVIRONMENT.md`
- `docs/PROMPT_EVAL_POLICY.md`
- `ai/eval/README.md`

## Project Structure

```
horadus/
├── AGENTS.md              # Canonical agent instructions (all CLIs)
├── CLAUDE.md              # Agent instructions (for Claude CLI)
├── README.md              # This file
├── PROJECT_STATUS.md      # Non-authoritative archive pointer stub
├── archive/               # Historical planning ledgers (opt-in only)
│   └── closed_tasks/      # Quarterly closed-task body archive shards (opt-in only)
├── pyproject.toml         # Python project config
├── docker-compose.yml     # Local infrastructure
├── docker-compose.prod.yml # Production deployment stack
├── alembic.ini            # Migration config
│
├── docker/                # Container definitions
│   ├── api/Dockerfile     # API container image
│   ├── worker/Dockerfile  # Worker/beat container image
│   └── postgres/Dockerfile# Postgres image with pgvector
│
├── docs/                  # Documentation
│   ├── ARCHITECTURE.md    # System design
│   ├── DATA_MODEL.md      # Database schema
│   ├── DEPLOYMENT.md      # Deployment runbook
│   ├── ENVIRONMENT.md     # Environment variable reference
│   ├── SECRETS_BACKENDS.md # Managed secret backend references
│   └── adr/               # Architecture decisions
│
├── ai/                    # AI assets (prompts, evals)
│
├── tasks/                 # Task tracking
│   ├── BACKLOG.md
│   ├── COMPLETED.md
│   ├── CURRENT_SPRINT.md
│   └── specs/
│
├── src/                   # Source code
│   ├── api/               # FastAPI app
│   ├── core/              # Domain logic
│   ├── ingestion/         # Data collectors
│   ├── processing/        # LLM, clustering
│   ├── storage/           # Database
│   └── workers/           # Celery tasks
│
├── tests/                 # Test suite
├── config/                # Configuration files
├── scripts/               # Utility scripts
└── alembic/               # Database migrations
```

## License

[Your License Here]

## Contributing

This is a personal learning project. If you want to propose changes, open an issue or a PR with a clear description and test notes.
