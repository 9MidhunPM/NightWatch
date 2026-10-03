# Frontend release

[Documentation index](README.md) · [Frontend development](frontend-development.md) · [Operations](operations.md) · [Health checks](health-checks.md)

A frontend release changes the public showcase and operator interface in the existing frontend service. Keep its rollout independent of the backend, restricted Docker observer, and persistent database.

## Build target and observed triggers

[The frontend Dockerfile](../frontend/Dockerfile) uses Node.js 24, installs from the lockfile, builds standalone output, copies public and compiled static assets, and starts the generated server as the `node` user. Its application port is 3000. The build context is `frontend/`, while Dokploy's configured Dockerfile path is `frontend/Dockerfile`; preserve that distinction when checking the platform's build settings.

For a local image build from the repository root:

```sh
docker build --file frontend/Dockerfile --tag nightwatch-frontend:candidate frontend
```

The hosted configuration was rechecked on 2026-10-03; these are settings to recheck before each release, not repository-enforced guarantees:

| Service | Observed push behavior |
| --- | --- |
| Frontend | Auto-deploy enabled; watch path `frontend/**`. |
| Backend | Auto-deploy enabled; watch paths `backend/**` and `.env.example`. |
| Restricted Docker observer | Auto-deploy disabled. |

The frontend source was `main`, with `nightwatch.midhunpm.in` routed over HTTPS to port 3000. Confirm the current source, branch, build context, domain, port, and watch paths in the intended existing project before publishing. Changes confined to `docs/` do not match these observed service watch paths, although the repository's push-triggered CI can still run.

When a matching push queues an automatic frontend deployment, inspect that deployment before starting another. A later manual deployment of the same commit can reuse build layers; establish the served revision and assets before diagnosing stale output.

## Preflight

1. Identify the intended revision and review the frontend changes. Confirm that credentials remain in private runtime configuration, with `NW_BACKEND_URL` pointing to the backend's private service address rather than frontend-container localhost.
2. Run the package checks and build under Node.js 24 as described in [Frontend development](frontend-development.md#run-the-package-checks). Build the frontend image when checking container delivery.
3. Exercise the production standalone output, including images, local font files, textures, and JavaScript chunks. A development-server preview alone does not verify the packaged asset layout.
4. Record the running frontend revision, available image digest, deployment result, and current public-page and readiness baseline. Retain the previous known-good image before replacing it, and confirm that the platform can redeploy that image.

## Browser and access checks

Use desktop, tablet, and narrow mobile viewports. Verify the actual rendered result and browser console after navigation, not only the initial response status.

- The public root renders without a session and retains its indexable metadata. Navigation anchors reach visible headings below the sticky header.
- On a supported desktop, the poster gives way to the scene after a successful render, and scrolling advances the illustrative incident. On mobile, reduced motion, disabled JavaScript, and unavailable WebGL, the complete narrative remains readable with a scene poster.
- Product tabs work by click and keyboard, including arrow keys, Home, and End. Engineering disclosures open with native controls. Focus stays visible, media captions distinguish recorded views, and result graphics retain their evidence.
- Public exploration makes no requests to `/api/backend/`, `/api/events`, or a model provider. Private infrastructure observations remain behind operator access.
- In a clean browser without a session, `/world` and the other console URLs redirect to `/login`; `/api/backend/world` and `/api/events` return `401`. Login and private routes retain `noindex, nofollow`. Indexing metadata is separate from session protection.
- Using the configured HTTPS origin, a valid operator login opens `/world`. Inspect populated observations, an incident detail, and the connection/polling state. This verification does not require sending an agent message or approving an infrastructure action.

The route and session details are documented in [Operator access](operator-access.md). Preserve private-page checks when changing public routing or search metadata.

## Runtime checks and rollback

Keep build, deployment, browser, and dependent-service results separate:

| Evidence | What it establishes |
| --- | --- |
| Build and deployment completion | The intended image was produced and the platform reports a deployment result. Check runtime logs and the served revision separately. |
| Frontend `/api/health` returns `200` | The frontend health route responds. This is the Docker image's health check. |
| Frontend `/api/ready` returns `200` | The configured backend health endpoint returned the expected JSON. It does not validate the access tokens or observation integrations. |
| Frontend `/api/ready` returns `503` | The frontend is responding but its backend check is degraded. The public page can still work; operator readiness is unresolved. |
| Authenticated observations | Actual source state, timestamps, and domain evidence establish which integrations and targets are available. |

[Health checks](health-checks.md) explains the endpoint behavior and safe GET commands. Retest after the platform switches traffic, and watch for missing chunks, failed image requests, session errors, and changed readiness rather than reporting success from an image build alone.

If the new frontend fails these gates, use the platform's supported procedure to restore the retained previous known-good frontend image digest. Preserve the established domain, port, network access, and private runtime configuration, then repeat the public, access-protection, and readiness checks against the restored artifact. Record the failed revision and rollback result so the next attempt has a concrete starting point.

A prior deployment entry alone does not prove that its image is still available. If the retained image cannot be selected, rebuild the known-good source revision and validate that artifact before switching traffic; do not promise an immediate image rollback without an available image.

Frontend rollback does not require a backend database restore or migration downgrade. Leave the backend service, SQLite volume, and observer unchanged. Backend/schema recovery is a separate operation covered by [Operations](operations.md#dokploy-service-setup).
