# NightWatch backend

NightWatch is a backend control plane for observable, evidence-gated service recovery.

## Local development

Install Python 3.12 and uv, copy `.env.example` to `.env`, then run:

```sh
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn nightwatch.main:app --reload
```

From `backend/`, validate with `uv run ruff check nightwatch ../tests`, `uv run mypy nightwatch`, and `uv run pytest ../tests ../tests/backend`.

## Deployment boundary

This repository contains the backend only. `compose.production.yml` starts one NightWatch backend service with its own persistent SQLite volume. A future frontend, PostgreSQL database, Redis instance, or worker must each be a separate Dokploy service with distinct NightWatch-specific names, volumes, and networks.

Do not use an existing NightWatch-Demo service, volume, network, deployment target, database, or secret with this repository.
