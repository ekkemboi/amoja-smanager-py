# Amoja Social Manager development tasks
.DEFAULT_GOAL := help

DB_PATH ?= instance/amoja-smanager.db
PYTEST_ENV ?= DATABASE_URL=sqlite:///:memory: TEST_DB=sqlite

.PHONY: help install init owner db-shell db-backup db-reset migrate migration \
	downgrade dev test lint lint-fix format format-check check clean

help: ## Show this help
	@echo "Amoja Social Manager"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Database: $(DB_PATH) (override with DATABASE_URL)"

install: ## Install Python dependencies with uv
	uv sync

init: install migrate ## Install dependencies and create the SQLite database

owner: ## Create the single owner account (prompts, or set AUTH_USERNAME/AUTH_PASSWORD)
	uv run flask --app src.app create-owner

db-shell: ## Open a sqlite3 shell on the database
	@test -f $(DB_PATH) || (echo "No database at $(DB_PATH). Run: make migrate"; exit 1)
	sqlite3 $(DB_PATH)

db-backup: ## Copy the SQLite database to backups/
	@test -f $(DB_PATH) || (echo "No database at $(DB_PATH). Run: make migrate"; exit 1)
	@mkdir -p backups
	sqlite3 $(DB_PATH) ".backup 'backups/amoja-smanager-$$(date +%Y%m%d-%H%M%S).db'"
	@echo "Backup written to backups/"

db-reset: ## Delete and recreate the database (requires CONFIRM=yes)
	@test "$(CONFIRM)" = "yes" || (echo "Refusing: run make db-reset CONFIRM=yes"; exit 1)
	rm -f $(DB_PATH) $(DB_PATH)-wal $(DB_PATH)-shm
	$(MAKE) migrate

migrate: ## Apply all database migrations
	uv run alembic upgrade head

migration: ## Create a migration: make migration m="message"
	@test -n "$(m)" || (echo 'Usage: make migration m="message"'; exit 1)
	uv run alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back the last migration
	uv run alembic downgrade -1

dev: ## Run the Flask development server on port 5000
	uv run python -m src.app

test: ## Run tests on an in-memory SQLite database
	$(PYTEST_ENV) uv run pytest tests/ -q

lint: ## Check code style with ruff
	uvx ruff check src web tests migrations

lint-fix: ## Apply safe ruff fixes
	uvx ruff check --fix src web tests migrations

format: ## Format Python code with ruff
	uvx ruff format src web tests migrations

format-check: ## Verify formatting without changing files
	uvx ruff format --check src web tests migrations

check: ## Compile sources and run tests
	uv run python -m compileall -q src web
	$(PYTEST_ENV) uv run pytest tests/ -q

clean: ## Remove caches and compiled Python files
	find src web tests migrations -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
	find src web tests migrations -type f -name '*.py[co]' -delete
