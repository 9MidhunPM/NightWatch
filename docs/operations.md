# Setup, deployment, and operation

[← README](../README.md) · [Architecture](architecture.md) · [Reference](reference.md)

## Local environment

Use Python 3.12 and Node.js 24 to match the repository constraints and CI. Install `uv`, then follow the root README commands. The backend resolves `.env` at the repository root; Next.js needs its own `frontend/.env.local` or injected process environment.

Generate distinct random values for the dashboard passphrase, session signing secret, frontend token, and operator token. Keep the two service-to-service tokens identical between frontend and backend. Do not commit either environment file.

For a simple credential generator:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Run it separately for each credential and enter the values in the appropriate private configuration. The dashboard passphrase is for login; the signing secret is not a login password.

## Configuration map

| Setting | Consumer | Purpose |
| --- | --- | --- |
| `NW_ENVIRONMENT` | Backend | Development/test/production validation mode |
| `NW_DATABASE_URL` | Backend | Async SQLite URL; production data must live on a persistent volume |
| `NW_BACKEND_URL` | Frontend | Backend base URL reachable from the frontend container |
| `NW_FRONTEND_ORIGIN` | Frontend | Exact allowed browser origin, including scheme and port |
| `NW_FRONTEND_TOKEN` | Both | Frontend-to-backend access header |
| `NW_OPERATOR_TOKEN` | Both | Authorization for privileged backend actions |
| `NW_DASHBOARD_PASSPHRASE` | Frontend | Private operator login |
| `NW_SESSION_SECRET` | Frontend | Session signing; at least 32 characters |
| `NW_CORS_ORIGINS`, `NW_WEBSOCKET_ORIGINS` | Backend | Comma-separated exact origins; HTTPS required in production |
| `NW_DOKPLOY_URL`, `NW_DOKPLOY_API_KEY` | Backend | Dokploy discovery and authorized operations |
| `NW_DOKPLOY_GITHUB_ID` | Backend | Connected Dokploy GitHub provider identifier |
| `NW_GITHUB_READ_TOKEN` | Backend | Optional private-repository inspection |
| `NW_BESZEL_URL`, `NW_BESZEL_SYSTEM_ID` | Backend | Beszel hub and target system |
| `NW_BESZEL_EMAIL`, `NW_BESZEL_PASSWORD` | Backend | Beszel authentication |
| `DOCKER_HOST` | Backend/Docker SDK | Private observer/proxy endpoint |
| `NW_CODEX_API_KEY` or `OPENAI_API_KEY` | Backend | Agent provider credential |
| `NW_CODEX_APP_SERVER_ENABLED` | Backend | Enable chat app-server integration |
| `NW_INVESTIGATOR_ENABLED` | Backend | Enable manual investigation capability |

The deployment secret catalog and disposable-target settings are specialized integrations; inspect `config.py` and `deployment_service.py` before enabling them. Secrets belong in deployment configuration, never in chat messages or tracked examples.

### Observation and model limits

The monitor defaults to a ten-second interval, a three-failure threshold, and a three-second probe timeout. The world service has its own observation/discovery cadence described in the architecture guide. These are different loops.

`NW_INVESTIGATOR_MAX_TOOL_CALLS` accepts **1–3**, default 3. `NW_INVESTIGATOR_MAX_OUTPUT_TOKENS` accepts **256–1200**, default 1200. The investigation timeout defaults to 45 seconds, with a configured maximum of 60. Do not reuse older examples with a twelve-call budget; current settings reject them.

## Dokploy service setup

Use a dedicated project and separate services. Do not reuse the old NightWatch demo’s database, volumes, secrets, or repair target.

| Service | Build configuration | Exposure and state |
| --- | --- | --- |
| Frontend | Dockerfile `frontend/Dockerfile`; context `frontend`; branch `main` | Port 3000 behind the HTTPS domain |
| Backend | Dockerfile `backend/Dockerfile`; context repository root; branch `main` | Private port 8000; persistent SQLite volume |
| Docker observer/proxy | Separately configured restricted observer | Private monitoring network; no public route |

Set frontend `NW_BACKEND_URL` to the backend’s private service address, not `localhost`: inside the frontend container, localhost refers to the frontend itself. Route `nightwatch.midhunpm.in` to frontend port 3000. Configure both token values on both services and use the public HTTPS origin consistently.

Mount the backend data volume at `/var/lib/nightwatch` and set:

```text
NW_DATABASE_URL=sqlite+aiosqlite:////var/lib/nightwatch/nightwatch.db
```

The backend image runs `alembic upgrade head` before starting Uvicorn. Preserve the database across container replacement and take a consistent SQLite backup before migrations. Use SQLite’s backup mechanism or stop writes during backup; copying a live file without accounting for its journal/WAL is not a reliable backup procedure.

The root `compose.production.yml` contains only the backend and its volume. It does **not** provision the frontend, Beszel, Dokploy, the Docker observer, or their networks. Those services and integration settings must be supplied separately.

## Check a deployment

1. Confirm the intended commit and `main` branch in Dokploy.
2. Read the build and runtime logs separately. “Image built” does not mean all integrations authenticated.
3. Check frontend `/api/health` and `/api/ready`; inspect readiness failures before opening the console.
4. Sign in and open the world, a populated incident list, and an incident detail page.
5. Confirm source timestamps and domain observations, not only status colors.
6. For an operational change, inspect its recorded result and the target’s runtime/public health separately.

## Troubleshooting

| Symptom | What to inspect |
| --- | --- |
| HTML returned where JSON is expected | Backend base URL, `/api/` path, reverse-proxy route, authentication redirect, response content type |
| “No fresh matching container” | Beszel system selection, sample timestamp, Docker identity, Dokploy app name, Compose child mapping |
| Login rejected by origin check | Exact `NW_FRONTEND_ORIGIN`, including protocol, hostname, and development port |
| Backend cannot authenticate frontend | Matching `NW_FRONTEND_TOKEN`; operator token for writes |
| Application start hangs | Current Dokploy lifecycle state; idle/error applications use the deploy path in NightWatch |
| Approval fails after a delay | Target may have changed since planning; prepare a new plan from current state |
| A page crashes after loading data | Browser exception and the populated data path; static build checks alone are insufficient |
| Incident list is quiet | Observation failure threshold, monitoring configuration, persisted records, and source freshness; model investigation is manual |
| No agent response | Provider credentials, app-server startup logs, timeout, and agent-status endpoint |

A cached Docker layer is not itself evidence of a stale deployment. Push-triggered builds and a later manual deployment of the same commit can legitimately reuse layers. Establish the deployed commit and served assets before diagnosing a cache problem.

## Validation commands

```sh
make check
make test
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Backend CI additionally validates a fresh migration chain, the Compose definition with required access settings, and the backend image. Frontend CI builds under Node 24. Keep test success, image build success, deployed service status, and browser behavior as separate pieces of evidence.
