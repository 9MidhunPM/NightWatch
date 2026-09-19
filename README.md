# NightWatch backend

NightWatch is a backend control plane for observable, evidence-gated service recovery. It collects narrow operational facts, records them as durable evidence, prepares one typed change, requires an operator's version-bound approval, and verifies the resulting state independently.

## How a recovery moves through NightWatch

```text
monitoring signal -> incident and evidence -> read-only investigator -> typed plan
                                                                  -> operator approval
                                                                  -> idempotent execution
                                                                  -> independent verification
```

The model is used for read-only investigation and operational synthesis. It has no shell, filesystem, Docker, or direct infrastructure authority. Mutations live in typed backend services and remain denied unless they are explicitly allowlisted and approved.

## Current capabilities

| Area | Behavior |
| --- | --- |
| Discovery | Local host, Docker, Traefik, Dokploy, Beszel, and HTTP observations form a topology snapshot. |
| Investigation | The Investigator uses bounded read-only tools, stores evidence, and cannot confirm a cause without persisted supporting evidence. |
| Repairs | The current mutable repair surface is an approved Traefik service-port patch for a designated disposable demo. |
| Deployments | Dokploy plans are version-bound, approval-gated, idempotent, and reconciled after ambiguous provider responses. |
| Recovery | Approved, running, and verifying workflows are persisted and reconciled on startup. |
| Realtime | WebSocket events and SSE activity expose workflow state without revealing model reasoning. |

## Operational boundaries

Protected and destructive actions are denied. NightWatch never offers a generic shell, SSH, firewall, volume, database, or deletion tool. Successful provider calls enter `VERIFYING`; they are not presented as resolved until independent checks pass. A deployment requires a healthy HTTPS response (2xx or redirect), and retries are bounded by configuration.

This repository contains only the backend. A future frontend, PostgreSQL database, Redis instance, or worker must each run as a separate Dokploy service with separate NightWatch-specific names, storage, and networking.

## Local development

Install Python 3.12 and uv, copy `.env.example` to `.env`, then run:

```sh
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn nightwatch.main:app --reload
```

From `backend/`, validate with `uv run ruff check nightwatch ../tests`, `uv run mypy nightwatch`, and `uv run pytest ../tests ../tests/backend`.

## Agent evaluation

The backend test suite covers authorization, typed tool dispatch, incident persistence, evidence gating, policy denial, stale approvals, deployment reconciliation, WebSocket behavior, and invalid inputs. Before changing the agent prompt, model, or tools, add a fixture-backed evaluation for:

- correct root-cause confirmation with concrete evidence;
- insufficient or contradictory evidence;
- unavailable or malformed tool results;
- attempts to obtain a destructive action;
- stale approval or restart recovery; and
- tool-call budget exhaustion and response latency.

Evaluate both the outcome and the recorded tool/evidence trajectory. Provider calls should be replaced with deterministic fixtures in CI.

## Deployment boundary

`compose.production.yml` starts one NightWatch backend service with its own persistent SQLite volume. Do not use an existing NightWatch-Demo service, volume, network, deployment target, database, or secret with this repository.
