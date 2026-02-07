# Geopolitical Intelligence Platform

A headless backend for collecting, classifying, and analyzing news to track geopolitical trend probabilities.

## Features

- **Multi-source ingestion**: RSS feeds, GDELT, Telegram channels
- **Smart filtering**: Two-tier LLM classification (cheap filter → expensive analysis)
- **Event clustering**: Groups duplicate news into single events
- **Trend tracking**: Bayesian-inspired probability updates using log-odds
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
cd geopolitical-intel

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

Authentication header (documented now, enforcement planned in TASK-025):
- `X-API-Key: <key>`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/trends` | List all trends with current probabilities |
| GET | `/api/v1/trends/{id}` | Get trend details |
| GET | `/api/v1/trends/{id}/history` | Get probability time series |
| GET | `/api/v1/trends/{id}/evidence` | Get events affecting trend |
| GET | `/api/v1/events` | List recent events |
| GET | `/api/v1/events/{id}` | Get event details |
| GET | `/api/v1/reports` | List generated reports |
| GET | `/api/v1/reports/{id}` | Get report details |

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
    keywords: ["troops", "deployment", "mobilization", "exercises", "nato"]

  sanctions:
    weight: 0.02
    direction: escalatory
    keywords: ["sanctions", "embargo", "restrictions", "freeze assets"]

  diplomatic_talks:
    weight: 0.03
    direction: de_escalatory
    keywords: ["talks", "negotiation", "summit", "agreement", "ceasefire"]

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

### Running Tests

```bash
# All tests
make test

# With coverage
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

## Project Structure

```
geopolitical-intel/
├── AGENTS.md              # Canonical agent instructions (all CLIs)
├── CLAUDE.md              # Agent instructions (for Claude CLI)
├── README.md              # This file
├── PROJECT_STATUS.md      # Development progress
├── pyproject.toml         # Python project config
├── docker-compose.yml     # Local infrastructure
├── alembic.ini            # Migration config
│
├── docs/                  # Documentation
│   ├── ARCHITECTURE.md    # System design
│   ├── DATA_MODEL.md      # Database schema
│   └── adr/               # Architecture decisions
│
├── ai/                    # AI assets (prompts, evals)
│
├── tasks/                 # Task tracking
│   ├── BACKLOG.md
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
