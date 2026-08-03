.PHONY: install local test lint clean container up down logs seed demo seed-local demo-local \
        cron-digest cron-digest-worker cron-outbox cron-reconcile migrate

# --- Local (host) development ---

install:
	@test -d .venv || uv venv
	@. .venv/bin/activate && uv pip install -e ".[dev]"
	@. .venv/bin/activate && pre-commit install
	@echo "Done. Activate with: source .venv/bin/activate"

# Runs the app directly on the host, using DATABASE_URL exactly as set in .env
# (loaded via python-dotenv in settings.py) - so this works equally against
# `make db` (local Postgres on localhost:5432) or a Supabase connection string.
local:
	@test -f .env || (echo "Creating .env from .env.example..." && cp .env.example .env)
	@. .venv/bin/activate && uvicorn smartreco_agent.src.api:app --host 0.0.0.0 --port 8000 --reload

# Run seed/demo scripts directly against whatever DATABASE_URL is in .env -
# use these (not `make seed`/`make demo`) when not running the app via Docker Compose.
seed-local:
	.venv/bin/python scripts/seed_catalog.py

demo-local:
	.venv/bin/python scripts/simulate_user.py

test:
	@if [ ! -d ".venv" ]; then echo "Run 'make install' first."; exit 1; fi
	.venv/bin/python -m pytest --cov=smartreco_agent --cov-report=term-missing

lint:
	.venv/bin/ruff check smartreco_agent tests scripts api

clean:
	@rm -rf .venv __pycache__ .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache build dist *.egg-info
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f \( -name "*.pyc" -o -name "*.pyo" -o -name ".DS_Store" \) -delete 2>/dev/null || true

# --- Docker Compose (reviewer path: `cp .env.example .env`, add MESH_API_KEY, then `make up`) ---

up:
	docker compose up --build -d
	@echo "Waiting for the app to become healthy..."
	@until curl -sf http://localhost:8000/health > /dev/null; do sleep 1; done
	@echo "SmartReco is up: http://localhost:8000"

down:
	docker compose down

logs:
	docker compose logs -f app

container: up

# Only the Postgres/pgvector container - useful alongside `make local`.
db:
	docker compose up -d db

# --- Data + demo ---

seed:
	docker compose exec app python scripts/seed_catalog.py

demo:
	docker compose exec app python scripts/simulate_user.py

# --- Cron endpoints (pg_cron drives these in prod; run by hand locally - §12.3) ---

CRON_SECRET ?= dev-cron-secret-change-me

cron-digest:
	curl -sX POST localhost:8000/api/cron/digest -H "x-cron-secret: $(CRON_SECRET)" | python3 -m json.tool

cron-digest-worker:
	curl -sX POST localhost:8000/api/cron/digest-worker -H "x-cron-secret: $(CRON_SECRET)" | python3 -m json.tool

cron-outbox:
	curl -sX POST localhost:8000/api/cron/outbox -H "x-cron-secret: $(CRON_SECRET)" | python3 -m json.tool

cron-reconcile:
	curl -sX POST localhost:8000/api/cron/reconcile -H "x-cron-secret: $(CRON_SECRET)" | python3 -m json.tool
