# Frontend development

[Operations](operations.md) · [Operator access](operator-access.md) · [Frontend release](frontend-release.md)

The public showcase and private operator console share one Next.js application. Start with the public page when working on presentation; add backend access only when testing operator behavior.

## Preview the public showcase

Use Node.js 24 and npm, matching [frontend CI](../.github/workflows/frontend.yml). From the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000/`. A fresh checkout needs no environment file, backend, passphrase, or integration credentials to render the showcase. Its scene and incident narrative are illustrative; product screenshots are recorded views. Public exploration does not call the private gateway, event stream, or a model provider.

The animated scene is enabled only for fine-pointer viewports at least 1024px wide with reduced motion disabled and WebGL 2 available. Smaller screens, reduced motion, unavailable WebGL, and scene failure retain the poster and readable chapters. Check both paths instead of treating an absent canvas as a failure. The navigation, product tabs, and engineering disclosures are also part of the preview.

## Add an operator environment

The backend reads the repository-root `.env`; Next.js reads `frontend/.env.local` or injected process variables. A root `.env` alone does not configure the frontend. Follow [Operations](operations.md#local-environment) for backend startup and the complete environment map; [the example](../.env.example) names the settings without supplying usable credentials.

The frontend needs these values for an operator preview:

| Setting | Local requirement |
| --- | --- |
| `NW_FRONTEND_ORIGIN` | The browser's exact origin, such as `http://localhost:3000`. |
| `NW_BACKEND_URL` | The reachable backend base address, normally `http://127.0.0.1:8000` locally. |
| `NW_DASHBOARD_PASSPHRASE` | A private operator passphrase. |
| `NW_SESSION_SECRET` | A distinct signing secret containing at least 32 characters. |
| `NW_FRONTEND_TOKEN` | Identical to the backend's frontend-access token. |
| `NW_OPERATOR_TOKEN` | Identical to the backend's operator token for privileged requests. |

Keep the two token pairs consistent between services, but use distinct values for the frontend token, operator token, passphrase, and signing secret. These are server variables; do not give them a `NEXT_PUBLIC_` prefix. Environment files are ignored by Git and excluded from the frontend Docker build context.

If you change the development port, update the frontend origin to match it. `localhost` and `127.0.0.1` are different hostnames; HTTP and HTTPS are different schemes. Keep the backend's allowed CORS and WebSocket origins consistent with the intended browser address. Restart the relevant processes after configuration changes so verification uses the new values.

Sign in at `/login`; success opens `/world`. Read a populated world and incident detail before concluding that the integration works. Login success and backend readiness alone do not prove that the token pair or observation sources are healthy. See [Operator access](operator-access.md) and [Health checks](health-checks.md) for those boundaries.

## Run the package checks

Run these from `frontend/`:

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

| Script | Purpose |
| --- | --- |
| `dev` | Next.js development server, binding to `0.0.0.0`. |
| `lint` | ESLint checks without rewriting files. |
| `typecheck` | TypeScript validation without emitting JavaScript. |
| `test` | Node's test runner through `tsx`, covering `tests/*.test.ts`. |
| `build` | Production build, generated route types, and standalone output. |
| `start` | Invokes `next start`; use the generated server below for this repository's standalone configuration. |

If a route rename leaves TypeScript errors referring to an old `.next/types` route, regenerate the route types with `npx next typegen`, then rerun `npm run typecheck`. Static checks do not replace browser verification; use the [release checklist](frontend-release.md#browser-and-access-checks) for representative interactions and fallbacks.

## Reproduce the standalone launch

The application uses `output: 'standalone'`. After a build, the generated server needs both public assets and compiled static assets beside it. From `frontend/`:

```sh
npm run build
cp -R public .next/standalone/
mkdir -p .next/standalone/.next
cp -R .next/static .next/standalone/.next/
PORT=3000 HOSTNAME=127.0.0.1 node .next/standalone/server.js
```

This reproduces the asset layout and generated-server entry point in [the Dockerfile](../frontend/Dockerfile). The Docker image already performs those copies and runs `node server.js`; it does not use the package's `start` script. The installed Next.js output guide describes this behavior at `frontend/node_modules/next/dist/docs/01-app/03-api-reference/05-config/01-next-config-js/output.md`.

For an operator standalone run, inject the required variables into the server process; do not assume the development environment file has been packaged. Production sessions use a `Secure` cookie, so validate authenticated production behavior over HTTPS. A plain HTTP standalone preview remains useful for the public page and asset checks.
