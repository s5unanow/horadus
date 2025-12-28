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
- Anthropic API key

### Setup

```bash
# Clone and enter project
git clone <repo-url>
cd geopolitical-intel

# Copy environment template
cp .env.example .env
# Edit .env with your API keys

# Start infrastructure
docker-compose up -d

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Seed initial trends
python scripts/seed_trends.py

# Start API server
uvicorn src.api.main:app --reload
```

### Start Workers

```bash
# In separate terminals:

# Celery worker (processes tasks)
celery -A src.workers.celery_app worker --loglevel=info

# Celery beat (schedules periodic tasks)
celery -A src.workers.celery_app beat --loglevel=info
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
    weight: -0.03
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

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
ruff format src/ tests/

# Lint
ruff check src/ tests/ --fix

# Type check
mypy src/
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Project Structure

```
geopolitical-intel/
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
│   ├── API_SPEC.md        # API documentation
│   └── adr/               # Architecture decisions
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

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
