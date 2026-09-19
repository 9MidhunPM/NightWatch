.PHONY: install migrate dev test check

install:
	UV_CACHE_DIR=/tmp/nightwatch-uv-cache uv sync --project backend --extra dev

migrate:
	cd backend && UV_CACHE_DIR=/tmp/nightwatch-uv-cache uv run alembic upgrade head

dev:
	cd backend && UV_CACHE_DIR=/tmp/nightwatch-uv-cache uv run uvicorn nightwatch.main:app --reload --host 127.0.0.1 --port 8000

test:
	cd backend && UV_CACHE_DIR=/tmp/nightwatch-uv-cache uv run pytest ../tests ../tests/backend

check:
	cd backend && UV_CACHE_DIR=/tmp/nightwatch-uv-cache uv run ruff check nightwatch ../tests
	cd backend && UV_CACHE_DIR=/tmp/nightwatch-uv-cache uv run mypy nightwatch
