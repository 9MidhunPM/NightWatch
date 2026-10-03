# Contributing to NightWatch

[Project README](README.md) · [Documentation index](docs/README.md)

NightWatch has a public showcase and a private operator console backed by separate frontend, backend, and Docker observer services. Start with the [architecture](docs/architecture.md) and [operations guide](docs/operations.md) before changing a service boundary.

## Choose the relevant part of the repository

| Area | Where to work | What to preserve |
| --- | --- | --- |
| Public showcase | `frontend/app/page.tsx`, `showcase.css`, `components/showcase-*`, `lib/showcase-*` | Readable static fallbacks and explicit simulated/recorded evidence labels |
| Operator experience | `frontend/app/(console)/`, other frontend components | Signed sessions, private routes, and unavailable/stale data states |
| Backend behavior | `backend/nightwatch/` | Typed contracts, policy, plan versions, approvals, target revalidation, and evidence |
| Tests | `frontend/tests/`, `tests/`, `tests/backend/` | Regression cases for observable behavior and failure paths |
| Documentation and media | `docs/`, `frontend/public/showcase/` | Source-grounded claims, provenance, useful links, and accessible descriptions |

[PRODUCT.md](PRODUCT.md) records the audience and product boundaries. [DESIGN.md](DESIGN.md) applies to the public showcase; it does not replace the private console's styling.

## Set up the part you need

Use Node.js 24 for frontend work and Python 3.12 with `uv` for backend work, matching the Dockerfiles and CI.

For a public-page change, the frontend can run without a backend or integration credentials:

```sh
cd frontend
npm ci
npm run dev
```

For backend or authenticated integration work, follow the [local setup](docs/operations.md#local-environment). The backend reads the root `.env`; Next.js reads `frontend/.env.local` or injected process variables. Configure exact origins and matching service tokens rather than sharing integration secrets with the browser.

Dependency changes should include the corresponding lockfile: `frontend/package-lock.json` or `backend/uv.lock`.

## Validate a change

Run the checks for the code you changed. Documentation-only changes need source verification, local link checks, and `git diff --check`; they do not need a running production integration.

Frontend checks, from `frontend/`:

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

Backend checks, from the repository root:

```sh
make install
make check
make test
```

For rendered changes, also exercise the affected browser interaction. Public-scene changes need desktop, mobile, reduced-motion, and unavailable-WebGL checks. A populated incident or plan view must be tested with representative data; an empty page does not exercise its formatting and action states.

Keep evidence separate: static checks, browser behavior, deployment status, and integration health answer different questions. A liveness response is not proof that an approved action recovered a public endpoint.

The [frontend workflow](.github/workflows/frontend.yml) runs lint, TypeScript, tests, and a build. The [backend workflow](.github/workflows/backend.yml) also checks a fresh migration chain, production Compose configuration, and the backend Docker image. Both currently run on pull requests and pushes to `main` without path filters.

## Extend operational behavior

Read the [API and workflow reference](docs/reference.md#extension-points) before exposing a new operation. Add typed inputs and adapter behavior, define the approval and stale-state checks, and specify which observations establish its outcome. Update the frontend proxy allowlist only when the route is intended to be browser-accessible.

Tests should cover the meaningful boundary: changed target state, rejected input, missing evidence, upstream failure, or the intended successful result. Keep external providers and real infrastructure mutations out of ordinary regression tests; use the project's fixture and fake-client patterns.

## Prepare a reviewable contribution

- Explain the concrete trigger and the resulting behavior, including relevant unavailable or failed states.
- Keep each commit focused on an independently useful change and stage only its paths. Leave unrelated work and source media untouched.
- Record the checks you actually ran and any integration or browser behavior you did not verify.
- Update the matching guide when setup, routes, contracts, or operational meaning changes.
- Preserve the creator's name as **Midhun P M** in product copy and documentation.

The existing release process uses separate services. Recheck deployment configuration before publishing; a frontend release should not require replacing the backend database or Docker observer.
