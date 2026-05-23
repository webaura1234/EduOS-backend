# ──────────────────────────────────────────────
# EduOS Backend — Makefile
# ──────────────────────────────────────────────

.PHONY: help dev migrate makemigrations shell test lint format docker-up docker-down celery beat seed

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ──────────────────────────────

dev: ## Run development server
	python manage.py runserver

migrate: ## Run database migrations
	python manage.py migrate

makemigrations: ## Create new migrations
	python manage.py makemigrations

shell: ## Open Django shell
	python manage.py shell_plus 2>/dev/null || python manage.py shell

createsuperuser: ## Create a superuser
	python manage.py createsuperuser

# ── Testing ──────────────────────────────────

test: ## Run tests
	pytest

test-cov: ## Run tests with coverage
	pytest --cov=apps --cov-report=html

# ── Code Quality ─────────────────────────────

lint: ## Run linter
	ruff check apps/ config/

format: ## Format code
	ruff format apps/ config/
	isort apps/ config/

typecheck: ## Run type checker
	mypy apps/ --ignore-missing-imports

# ── Docker ───────────────────────────────────

docker-up: ## Start all services via Docker Compose
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-logs: ## Tail Docker logs
	docker compose logs -f

docker-build: ## Build Docker images
	docker compose build

# ── Celery ───────────────────────────────────

celery: ## Start Celery worker
	celery -A config worker -l info -Q default,high,low

beat: ## Start Celery beat scheduler
	celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

# ── Data ─────────────────────────────────────

seed: ## Seed demo data
	python manage.py seed_demo_data

flush: ## Flush database (DESTRUCTIVE)
	python manage.py flush --no-input

# ── Deployment ───────────────────────────────

collectstatic: ## Collect static files
	python manage.py collectstatic --noinput

check: ## Run Django system checks
	python manage.py check --deploy
