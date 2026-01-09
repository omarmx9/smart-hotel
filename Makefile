# Smart Hotel Project Makefile
# Usage: make <target>

.PHONY: help install test lint format clean docker-up docker-down docker-build \
        test-dashboard test-kiosk test-mrz migrate

# Default target
help:
	@echo "Smart Hotel Development Commands"
	@echo "================================="
	@echo ""
	@echo "Setup:"
	@echo "  make install         Install all dependencies"
	@echo "  make install-dev     Install development dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test            Run all tests"
	@echo "  make test-dashboard  Run dashboard tests"
	@echo "  make test-kiosk      Run kiosk tests"
	@echo "  make test-mrz        Run MRZ backend tests"
	@echo "  make coverage        Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint            Run linters (ruff)"
	@echo "  make format          Format code (black, isort)"
	@echo "  make check           Run all checks (lint + test)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up       Start all services"
	@echo "  make docker-down     Stop all services"
	@echo "  make docker-build    Build all images"
	@echo "  make docker-logs     View service logs"
	@echo ""
	@echo "Django:"
	@echo "  make migrate         Run database migrations"
	@echo "  make collectstatic   Collect static files"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           Remove temporary files"

# Installation
install:
	cd dashboards/django_app && pip install -r requirements.txt
	cd kiosk && pip install -r requirements.txt
	cd kiosk/app && pip install -r requirements.txt

install-dev:
	pip install pre-commit ruff black isort pytest pytest-cov
	cd dashboards/django_app && pip install -r requirements-test.txt
	cd kiosk && pip install -r requirements-test.txt
	cd kiosk/app && pip install -r requirements-test.txt
	pre-commit install

# Testing
test: test-dashboard test-kiosk test-mrz

test-dashboard:
	cd dashboards/django_app && python -m pytest -v

test-kiosk:
	cd kiosk && python -m pytest -v

test-mrz:
	cd kiosk/app && python -m pytest -v

coverage:
	cd dashboards/django_app && python -m pytest --cov=. --cov-report=html
	cd kiosk && python -m pytest --cov=. --cov-report=html
	cd kiosk/app && python -m pytest --cov=. --cov-report=html

# Code Quality
lint:
	ruff check dashboards/django_app kiosk

format:
	black dashboards/django_app kiosk
	isort dashboards/django_app kiosk
	ruff check --fix dashboards/django_app kiosk

check: lint test

# Pre-commit
pre-commit:
	pre-commit run --all-files

# Docker
docker-up:
	cd cloud && docker compose up -d

docker-down:
	cd cloud && docker compose down

docker-build:
	cd cloud && docker compose build

docker-logs:
	cd cloud && docker compose logs -f

docker-restart:
	cd cloud && docker compose restart

# Django
migrate:
	cd dashboards/django_app && python manage.py migrate
	cd kiosk && python manage.py migrate

collectstatic:
	cd dashboards/django_app && python manage.py collectstatic --noinput
	cd kiosk && python manage.py collectstatic --noinput

createsuperuser:
	cd dashboards/django_app && python manage.py createsuperuser

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Development servers (for local development without Docker)
run-dashboard:
	cd dashboards/django_app && python manage.py runserver 0.0.0.0:8001

run-kiosk:
	cd kiosk && python manage.py runserver 0.0.0.0:8002

run-mrz:
	cd kiosk/app && python app.py
