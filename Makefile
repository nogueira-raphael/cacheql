.PHONY: help install install-dev test test-cov lint format typecheck check clean build publish

# Default target
help:
	@echo "CacheQL Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install package in development mode"
	@echo "  make install-dev  Install with all dev dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run tests"
	@echo "  make test-cov     Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         Run linter (ruff)"
	@echo "  make format       Format code (ruff)"
	@echo "  make typecheck    Run type checker (mypy)"
	@echo "  make check        Run all checks (lint + typecheck + test)"
	@echo ""
	@echo "Build:"
	@echo "  make clean        Remove build artifacts"
	@echo "  make build        Build package"
	@echo "  make publish      Publish to PyPI (requires credentials)"

# Setup
install:
	uv sync

install-dev:
	uv sync --all-extras

# Testing
test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=cacheql --cov-report=term-missing --cov-report=html --cov-report=xml

# Code Quality
lint:
	uv run ruff check src/ tests/

format:
	uv run ruff check src/ tests/ --fix
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/cacheql --ignore-missing-imports

check: lint typecheck test

# Build
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -f coverage.xml
	rm -f .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

build: clean
	uv build

publish: build
	uv publish
