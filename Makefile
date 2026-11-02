PY ?= python
VENV = .venv
BIN = $(VENV)/Scripts

.PHONY: help setup install lint format typecheck test test-cov check api worker api-types check-api-types cli clean

help:
	@echo "setup      - create venv and install dev dependencies"
	@echo "lint       - ruff lint"
	@echo "format     - ruff format"
	@echo "typecheck  - mypy"
	@echo "test       - pytest"
	@echo "check      - lint + typecheck + test"
	@echo "api        - run the FastAPI dev server"
	@echo "api-types  - regenerate the frontend API types after an API schema change"
	@echo "worker     - run the analysis worker (needs DATABASE_URL)"
	@echo "cli        - run the demo verification on the Kariba case"

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e "packages/groundtruth[api,db,genai,dev]"

lint:
	ruff check packages tests

format:
	ruff format packages tests
	ruff check --fix packages tests

typecheck:
	mypy

test:
	pytest

test-cov:
	pytest --cov --cov-report=term-missing

check: lint typecheck test

api:
	uvicorn apps.api.main:app --reload --port 8000

api-types:
	$(PY) apps/web/scripts/export_openapi.py
	cd apps/web && npm run generate:api

check-api-types:
	$(PY) -m pytest -q tests/test_openapi_snapshot.py
	cd apps/web && npm run check:api-types

worker:
	python -m apps.worker.main

cli:
	groundtruth verify kariba-redd --synthetic

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage build dist
