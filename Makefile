# =============================================================================
# Geopolitical Intelligence Platform - Makefile
# =============================================================================
# Usage: make <target>
# Run `make help` to see all available targets
# =============================================================================

.PHONY: help venv deps deps-dev hooks install install-dev setup clean \
        format lint typecheck test test-unit test-integration test-cov \
        docker-up docker-down docker-logs docker-prod-build docker-prod-up \
        docker-prod-down docker-prod-migrate backup-db restore-db verify-backups db-migrate db-upgrade db-downgrade \
        run run-worker run-beat export-dashboard benchmark-eval benchmark-eval-human validate-taxonomy-eval audit-eval docs-freshness pre-commit check all \
        db-migration-gate branch-guard protect-main

# Default target
.DEFAULT_GOAL := help

# Tooling
VENV ?= .venv
VENV_PY := $(VENV)/bin/python
UV ?= uv
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
export UV_CACHE_DIR
UV_RUN := $(UV) run --no-sync
PYTHON := $(shell command -v python3.12 >/dev/null 2>&1 && echo python3.12 || echo python3)
DOCKER_COMPOSE := $(shell if command -v docker-compose >/dev/null 2>&1; then echo docker-compose; else echo "docker compose"; fi)
INTEGRATION_DATABASE_URL ?= postgresql+asyncpg://postgres:postgres@localhost:5432/geoint_test  # pragma: allowlist secret
INTEGRATION_REDIS_URL ?= redis://localhost:6379/0
MIGRATION_GATE_DATABASE_URL ?= $(INTEGRATION_DATABASE_URL)
MIGRATION_GATE_VALIDATE_AUTOGEN ?= true

# Colors for terminal output
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

# =============================================================================
# Help
# =============================================================================

help: ## Show this help message
	@echo "$(BLUE)Geopolitical Intelligence Platform$(RESET)"
	@echo ""
	@echo "$(GREEN)Available targets:$(RESET)"
	@awk 'BEGIN {FS = ":.*##"; printf ""} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# =============================================================================
# Installation
# =============================================================================

venv: ## Create local virtualenv at .venv (prefers uv)
	@command -v $(UV) >/dev/null 2>&1 || (echo "$(RED)uv is required.$(RESET) Install uv via Nix and retry." && exit 1)
	@test -x "$(VENV_PY)" || $(UV) venv --python $(PYTHON) $(VENV)

deps: venv ## Install production dependencies (prefers uv)
	$(UV) sync --python $(VENV_PY)

deps-dev: venv ## Install development dependencies (prefers uv)
	$(UV) sync --extra dev --python $(VENV_PY)

hooks: deps-dev ## Install git hooks (pre-commit + commit-msg)
	$(UV_RUN) pre-commit install
	$(UV_RUN) pre-commit install --hook-type pre-push
	$(UV_RUN) pre-commit install --hook-type commit-msg

install: deps ## Back-compat alias for deps

install-dev: deps-dev hooks ## Back-compat alias for deps-dev + hooks

setup: deps-dev hooks docker-up db-upgrade ## Full development setup
	@echo "$(GREEN)Setup complete!$(RESET)"
	@echo "Run 'make run' to start the API server"

# =============================================================================
# Code Quality
# =============================================================================

format: deps-dev ## Format code with ruff
	$(UV_RUN) ruff format src/ tests/
	$(UV_RUN) ruff check src/ tests/ --fix

lint: deps-dev ## Run linter (ruff)
	$(UV_RUN) ruff check src/ tests/

typecheck: deps-dev ## Run type checker (mypy)
	$(UV_RUN) mypy src/

check: format lint typecheck ## Run all code quality checks
	@echo "$(GREEN)All checks passed!$(RESET)"

pre-commit: ## Run pre-commit on all files
	$(UV_RUN) pre-commit run --all-files

branch-guard: ## Validate current branch naming policy
	./scripts/check_branch_name.sh

protect-main: ## Apply required main-branch protection + merge policy (requires gh auth)
	./scripts/enforce_main_protection.sh

# =============================================================================
# Testing
# =============================================================================

test: deps-dev ## Run all tests
	$(UV_RUN) pytest tests/ -v

test-unit: deps-dev ## Run unit tests only
	$(UV_RUN) pytest tests/unit/ -v -m unit

test-integration: deps-dev ## Run integration tests only
	DATABASE_URL="$(INTEGRATION_DATABASE_URL)" $(UV_RUN) alembic upgrade head
	DATABASE_URL="$(INTEGRATION_DATABASE_URL)" MIGRATION_GATE_VALIDATE_AUTOGEN="$(MIGRATION_GATE_VALIDATE_AUTOGEN)" ./scripts/check_migration_drift.sh
	DATABASE_URL="$(INTEGRATION_DATABASE_URL)" REDIS_URL="$(INTEGRATION_REDIS_URL)" $(UV_RUN) pytest tests/integration/ -v -m integration

test-cov: deps-dev ## Run tests with coverage report
	$(UV_RUN) pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)Coverage report: htmlcov/index.html$(RESET)"

# =============================================================================
# Docker / Infrastructure
# =============================================================================

docker-up: ## Start Docker containers (postgres, redis)
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)Waiting for services to be ready...$(RESET)"
	@sleep 3
	@$(DOCKER_COMPOSE) ps

docker-down: ## Stop Docker containers
	$(DOCKER_COMPOSE) down

docker-logs: ## Show Docker container logs
	$(DOCKER_COMPOSE) logs -f

docker-clean: ## Stop containers and remove volumes
	$(DOCKER_COMPOSE) down -v
	@echo "$(YELLOW)Warning: All data has been removed$(RESET)"

docker-prod-build: ## Build production images
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml build

docker-prod-migrate: ## Run production database migrations (one-off)
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml --profile ops run --rm migrate

docker-prod-up: ## Start production stack
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml up -d api worker beat postgres redis

docker-prod-down: ## Stop production stack
	$(DOCKER_COMPOSE) -f docker-compose.prod.yml down

backup-db: ## Create compressed PostgreSQL backup from production stack
	./scripts/backup_postgres.sh

restore-db: ## Restore PostgreSQL backup (usage: make restore-db DUMP=backups/file.sql.gz)
	@test -n "$(DUMP)" || (echo "$(RED)Usage: make restore-db DUMP=backups/<file>.sql.gz$(RESET)" && exit 1)
	./scripts/restore_postgres.sh "$(DUMP)"

verify-backups: ## Verify latest PostgreSQL backup freshness/integrity
	./scripts/verify_backups.sh

# =============================================================================
# Database
# =============================================================================

db-migrate: deps ## Create new migration (usage: make db-migrate msg="description")
	$(UV_RUN) alembic revision --autogenerate -m "$(msg)"

db-upgrade: deps ## Apply all pending migrations
	$(UV_RUN) alembic upgrade head

db-downgrade: deps ## Rollback last migration
	$(UV_RUN) alembic downgrade -1

db-history: deps ## Show migration history
	$(UV_RUN) alembic history --verbose

db-current: deps ## Show current migration
	$(UV_RUN) alembic current

db-migration-gate: deps ## Fail if target DB revision drifts from Alembic head or model state
	DATABASE_URL="$(MIGRATION_GATE_DATABASE_URL)" MIGRATION_GATE_VALIDATE_AUTOGEN="$(MIGRATION_GATE_VALIDATE_AUTOGEN)" ./scripts/check_migration_drift.sh

# =============================================================================
# Run Application
# =============================================================================

run: deps ## Run API server (development mode)
	$(UV_RUN) uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

run-worker: ## Run Celery worker
	$(UV_RUN) celery -A src.workers.celery_app worker --loglevel=info

run-beat: ## Run Celery beat scheduler
	$(UV_RUN) celery -A src.workers.celery_app beat --loglevel=info

export-dashboard: deps ## Export static calibration dashboard artifacts
	$(UV_RUN) horadus dashboard export

benchmark-eval: deps ## Run Tier-1/Tier-2 benchmark against gold set
	$(UV_RUN) horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 50

benchmark-eval-human: deps ## Run benchmark using only human-verified labels
	$(UV_RUN) horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200 --require-human-verified

validate-taxonomy-eval: deps ## Validate trend taxonomy contract against eval gold set
	$(UV_RUN) horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode subset --signal-type-mode warn --unknown-trend-mode warn

audit-eval: validate-taxonomy-eval ## Audit evaluation dataset quality and provenance
	$(UV_RUN) horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 200

docs-freshness: deps ## Validate docs freshness and runtime consistency invariants
	$(UV_RUN) python scripts/check_docs_freshness.py

# =============================================================================
# Security
# =============================================================================

security: deps-dev ## Run security checks (bandit)
	$(UV_RUN) bandit -c pyproject.toml -r src/

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Remove build artifacts and caches
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)Cleaned!$(RESET)"

# =============================================================================
# Composite Targets
# =============================================================================

all: check test ## Run all checks and tests
	@echo "$(GREEN)All checks and tests passed!$(RESET)"

ci: ## CI pipeline (format check, lint, typecheck, test)
	$(UV_RUN) ruff format src/ tests/ --check
	$(UV_RUN) ruff check src/ tests/
	$(UV_RUN) mypy src/
	$(UV_RUN) pytest tests/ -v --cov=src
