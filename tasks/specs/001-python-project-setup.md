# TASK-001: Python Project Setup

## Overview

Set up the Python project structure with all dependencies, development tools, and package configuration.

## Context

This is the foundation task. Everything else depends on having a properly configured Python project. We're using modern Python tooling (pyproject.toml, ruff, mypy).

## Requirements

### Dependencies (Production)

```toml
# Core
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"

# Database
asyncpg = "^0.29.0"
sqlalchemy = {extras = ["asyncio"], version = "^2.0.25"}
alembic = "^1.13.0"
pgvector = "^0.2.4"

# Task Queue
celery = {extras = ["redis"], version = "^5.3.0"}
redis = "^5.0.0"

# HTTP Client
httpx = "^0.26.0"

# Data Processing
feedparser = "^6.0.10"
trafilatura = "^1.6.0"

# LLM
openai = "^1.0.0"

# Utilities
python-dotenv = "^1.0.0"
structlog = "^24.1.0"
```

### Dependencies (Development)

```toml
# Testing
pytest = "^8.0.0"
pytest-asyncio = "^0.23.0"
pytest-cov = "^4.1.0"

# Code Quality
ruff = "^0.2.0"
mypy = "^1.8.0"

# Type Stubs
types-redis = "^4.6.0"
```

### Project Structure

After this task, the following should exist and be importable:

```
src/
├── __init__.py
├── api/
│   ├── __init__.py
│   └── routes/
│       └── __init__.py
├── core/
│   └── __init__.py
├── ingestion/
│   └── __init__.py
├── processing/
│   └── __init__.py
├── storage/
│   └── __init__.py
└── workers/
    └── __init__.py
```

### Environment Variables (.env.example)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/geoint

# Redis
REDIS_URL=redis://localhost:6379/0

# API
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true

# LLM
OPENAI_API_KEY=sk-your-key-here

# Optional: GDELT
GDELT_API_KEY=

# Optional: Telegram
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION_NAME=geoint_session
```

## Implementation Steps

1. Create `pyproject.toml` with all dependencies and tool configs
2. Create `.env.example` with all environment variables
3. Create all `__init__.py` files in src/ packages
4. Verify installation: `uv sync --extra dev`
5. Verify imports work: `python -c "from src.api import main"`

## pyproject.toml Template

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "geopolitical-intel"
version = "0.1.0"
description = "Geopolitical intelligence platform"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    # ... (see above)
]

[project.optional-dependencies]
dev = [
    # ... (see above)
]

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
```

## Verification

```bash
# Install project
uv sync --extra dev

# Verify imports
python -c "from src.api import main; print('API module OK')"
python -c "from src.core import config; print('Core module OK')"
python -c "from src.storage import models; print('Storage module OK')"

# Verify tools
uv run --extra dev ruff check src/
uv run --extra dev mypy src/
uv run --extra dev pytest --version
```

## Acceptance Checklist

- [ ] `pyproject.toml` created with all dependencies
- [ ] `.env.example` created with all variables
- [ ] All `src/**/__init__.py` files created
- [ ] `uv sync --extra dev` succeeds
- [ ] `python -c "import src"` works
- [ ] `uv run --extra dev ruff check src/` runs (may have no files to check yet)
- [ ] `uv run --extra dev mypy src/` runs (may have no files to check yet)
