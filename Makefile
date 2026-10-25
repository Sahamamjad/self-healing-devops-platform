PYTHON ?= python3.12
VENV ?= .venv
BIN := $(VENV)/bin
export PYTHONPATH := src

.PHONY: venv install lint test migrate run compose-up compose-down smoke verify clean

venv:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: venv
	$(BIN)/pip install -e ".[dev]"

lint:
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests
	$(BIN)/bandit -r src -c pyproject.toml

test:
	$(BIN)/pytest --cov=self_healing_platform --cov-report=term-missing

migrate:
	$(BIN)/alembic upgrade head

run:
	$(BIN)/alembic upgrade head
	$(BIN)/python -m self_healing_platform

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

smoke:
	$(BIN)/python scripts/smoke_test.py

verify:
	$(BIN)/python scripts/verify.py

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .coverage htmlcov data/*.sqlite
