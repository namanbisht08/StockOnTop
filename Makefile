.PHONY: help install test lint format clean migrate seed download-data backtest weekly-scan daily-update run

help:
	@echo "Available commands:"
	@echo "  install       - Install dependencies"
	@echo "  test          - Run tests"
	@echo "  lint          - Run ruff linter"
	@echo "  format        - Run ruff formatter"
	@echo "  clean         - Remove cache files"
	@echo "  migrate       - Run database migrations"
	@echo "  seed          - Seed database with initial universe"
	@echo "  download-data - Download historical data for universe"
	@echo "  backtest      - Run backtester"
	@echo "  weekly-scan   - Run weekly scanner"
	@echo "  daily-update  - Check open positions and send status digest"
	@echo "  run           - Run the API server"

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .ruff_cache

migrate:
	alembic upgrade head

seed:
	PYTHONPATH=. python scripts/seed_universe.py

download-data:
	PYTHONPATH=. python scripts/download_history.py

backtest:
	PYTHONPATH=. python scripts/run_backtest.py

weekly-scan:
	PYTHONPATH=. python scripts/run_weekly_scan.py

daily-update:
	PYTHONPATH=. python scripts/run_daily_update.py

run:
	uvicorn app.main:app --reload
