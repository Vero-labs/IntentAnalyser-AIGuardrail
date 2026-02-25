.PHONY: install dev test lint docker compose-up compose-down compose-dev binary clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install package in editable mode with dev dependencies
	pip install -e ".[dev]"

dev: ## Start dev server with hot-reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run test suite
	python -m pytest tests/ -v

lint: ## Run linter
	ruff check app/ tests/

lint-fix: ## Run linter with auto-fix
	ruff check --fix app/ tests/

docker: ## Build Docker image
	docker build -t intent-llm-gateway:latest .

compose-up: ## Start full stack (gateway + redis)
	docker compose -f docker-compose.gateway.yml up --build -d

compose-down: ## Stop full stack
	docker compose -f docker-compose.gateway.yml down

compose-dev: ## Start dev stack with hot-reload
	docker compose -f docker-compose.dev.yml up --build

binary: ## Build standalone binary with PyInstaller
	./scripts/build-binary.sh

init: ## Run interactive setup wizard
	python -m app.policy_cli init

doctor: ## Check system health
	python -m app.policy_cli doctor

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info __pycache__ .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
