# NightWatch

NightWatch is a private infrastructure world and evidence-gated operations console. The FastAPI control plane observes Dokploy, Docker, domains, incidents, and approval-bound changes. The Next.js frontend turns that evidence into an explorable 3D project map and focused operational workflows.

## Local development

Install Python 3.12 and uv, copy `.env.example` to `.env`, then run:

```sh
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn nightwatch.main:app --reload
```

From `backend/`, validate with `uv run ruff check nightwatch ../tests`, `uv run mypy nightwatch`, and `uv run pytest ../tests ../tests/backend`.

## Frontend development

```sh
cd frontend
npm ci
npm run dev
```

The browser talks only to allowlisted Next.js server routes. `NW_FRONTEND_TOKEN`, `NW_OPERATOR_TOKEN`, the dashboard passphrase, and provider credentials stay server-side.

## Production services

Deploy this repository as three independent services in a new Dokploy project:

- `nightwatch-frontend`, built from `frontend/Dockerfile`, serves HTTPS on port 3000.
- `nightwatch-backend`, built from `backend/Dockerfile`, remains private on port 8000 and owns a dedicated SQLite volume at `/var/lib/nightwatch`.
- `nightwatch-docker-proxy` runs the Docker socket proxy with read-only API sections. It is private and reachable only by the backend through the monitoring network.

The frontend and backend share a private application network. The backend and Docker proxy share a separate private monitoring network. The backend uses `DOCKER_HOST=tcp://nightwatch-docker-proxy:2375`; do not mount the Docker socket directly into the NightWatch backend.

Do not use an existing NightWatch-Demo service, volume, network, deployment target, database, or secret with this repository.
