.PHONY: local dev test clean deploy

# Dependency checks
deps:
	@which uv > /dev/null && echo "uv: $(shell uv --version)" || (echo "Error: uv not found. Please install uv." && exit 1)
	@which podman > /dev/null && echo "podman: $(shell podman --version)" || (echo "Error: podman not found. Please install podman." && exit 1)
	@which podman-compose > /dev/null && echo "podman-compose: $(shell podman-compose --version)" || (echo "Error: podman-compose not found. Please install podman-compose." && exit 1)

# Install Python dependencies
install:
	@echo "Creating virtual environment..."
	@test -d .venv || uv venv
	@echo "Installing package with dev dependencies..."
	@. .venv/bin/activate && uv pip install -e ".[dev]"
	@echo "Installing pre-commit hooks..."
	@. .venv/bin/activate && pre-commit install
	@echo "Python dependencies installed successfully!"
	@echo "Activating virtual environment..."
	@echo '#!/bin/bash' > /tmp/activate_and_shell.sh
	@echo 'source .venv/bin/activate' >> /tmp/activate_and_shell.sh
	@echo 'echo "Virtual environment activated! Type exit to return to your original shell."' >> /tmp/activate_and_shell.sh
	@echo 'exec "$$SHELL"' >> /tmp/activate_and_shell.sh
	@chmod +x /tmp/activate_and_shell.sh
	@exec /tmp/activate_and_shell.sh

clean:
	@echo "Cleaning up non-code artifacts..."
	@rm -rf .venv
	@rm -rf __pycache__
	@rm -rf .pytest_cache
	@rm -rf .coverage
	@rm -rf htmlcov
	@rm -rf .mypy_cache
	@rm -rf .ruff_cache
	@rm -rf build
	@rm -rf dist
	@rm -rf *.egg-info
	@rm -f Current-IT-Root-CAs.pem
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".DS_Store" -delete 2>/dev/null || true
	@echo "Cleanup complete"

test:
	@if [ ! -d ".venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make install' first to set up the environment."; \
		exit 1; \
	fi
	.venv/bin/python -m pytest

local:
	@echo "Setting up local environment..."
	@test -f .env || (echo "Creating .env from .env.example..." && cp .env.example .env)
	@echo "Starting MCP server locally on port 5002..."
	@echo "Health check available at: http://localhost:5002/health"
	@echo "Press Ctrl+C to stop the server"
	@. .venv/bin/activate && USE_INMEMORY_SAVER=true python -m smartreco_agent.src.main

container:
	export PODMAN_COMPOSE_SILENT=true
	podman-compose --no-ansi up --build --force-recreate --remove-orphans  --timeout=60

# Deployment
deploy:
	@$(MAKE) container
