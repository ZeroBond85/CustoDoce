# Makefile for CustoDoce
# Standardized commands for development, testing, and deployment

.PHONY: all lint typecheck test-unit test-int test-e2e test-real quality deploy schema db-audit clean

# Default target
all: lint typecheck test-unit

# --- Quality & Linting ---

lint:
	ruff check .
	bandit -r admin/ dashboard/ services/ -x tests/
	pip-audit --strict

typecheck:
	python -m mypy . --config-file pyproject.toml

# --- Testing ---

test-unit:
	python -m pytest tests/unit/ tests/schema/ -q

test-int:
	python -m pytest tests/integration/ -q --tb=short

test-e2e:
	python -m pytest tests/e2e/ -q

test-real:
	python -m pytest tests/real/ -q

# New quality gate check
quality:
	python -m pytest tests/unit/ tests/schema/ -q
	ruff check .
	python -m mypy . --config-file pyproject.toml

# --- Database & Deployment ---

deploy:
	python scripts/deploy_database.py --execute

schema:
	python scripts/validate_db_schema.py

db-audit:
	python scripts/db_audit.py

# --- Utility ---

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || powershell -Command "Get-ChildItem -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force"
	rm -rf .mypy_cache .pytest_cache 2>/dev/null || powershell -Command "Remove-Item -Recurse -Force .mypy_cache, .pytest_cache" -ErrorAction SilentlyContinue
