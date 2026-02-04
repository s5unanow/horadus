# =============================================================================
# Geopolitical Intelligence Platform - Makefile
# =============================================================================
# Usage: make <target>
# Run `make help` to see all available targets
# =============================================================================

.PHONY: help install install-dev setup clean \
        format lint typecheck test test-unit test-integration test-cov \
        docker-up docker-down docker-logs db-migrate db-upgrade db-downgrade \
        run run-worker run-beat pre-commit check all

# Default target
.DEFAULT_GOAL := help

# Tooling
PYTHON ?= python3
DOCKER_COMPOSE := $(shell if command -v docker-compose >/dev/null 2>&1; then echo docker-compose; else echo "docker compose"; fi)

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

install: ## Install production dependencies
	pip install -e .

install-dev: ## Install development dependencies
	pip install -e ".[dev]"
	pre-commit install
	pre-commit install --hook-type commit-msg

setup: install-dev docker-up db-upgrade ## Full development setup
	@echo "$(GREEN)Setup complete!$(RESET)"
	@echo "Run 'make run' to start the API server"

# =============================================================================
# Code Quality
# =============================================================================

format: ## Format code with ruff
	ruff format src/ tests/
	ruff check src/ tests/ --fix

lint: ## Run linter (ruff)
	ruff check src/ tests/

typecheck: ## Run type checker (mypy)
	mypy src/

check: format lint typecheck ## Run all code quality checks
	@echo "$(GREEN)All checks passed!$(RESET)"

pre-commit: ## Run pre-commit on all files
	pre-commit run --all-files

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v

test-unit: ## Run unit tests only
	$(PYTHON) -m pytest tests/unit/ -v -m unit

test-integration: ## Run integration tests only
	$(PYTHON) -m pytest tests/integration/ -v -m integration

test-cov: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
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

# =============================================================================
# Database
# =============================================================================

db-migrate: ## Create new migration (usage: make db-migrate msg="description")
	alembic revision --autogenerate -m "$(msg)"

db-upgrade: ## Apply all pending migrations
	alembic upgrade head

db-downgrade: ## Rollback last migration
	alembic downgrade -1

db-history: ## Show migration history
	alembic history --verbose

db-current: ## Show current migration
	alembic current

# =============================================================================
# Run Application
# =============================================================================

run: ## Run API server (development mode)
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

run-worker: ## Run Celery worker
	celery -A src.workers.celery_app worker --loglevel=info

run-beat: ## Run Celery beat scheduler
	celery -A src.workers.celery_app beat --loglevel=info

# =============================================================================
# Security
# =============================================================================

security: ## Run security checks (bandit)
	bandit -c pyproject.toml -r src/

deps-check: ## Check for vulnerable dependencies
	pip-audit

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
	ruff format src/ tests/ --check
	ruff check src/ tests/
	mypy src/
	$(PYTHON) -m pytest tests/ -v --cov=src
