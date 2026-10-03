# Health checks and observed evidence

[Documentation index](README.md) · [← README](../README.md) · [Operations](operations.md)

NightWatch's HTTP checks answer different questions. A responding frontend, a reachable backend, fresh infrastructure observations, and a healthy public application are separate pieces of evidence.

## What each endpoint proves

| Endpoint | Check performed | Successful result |
| --- | --- | --- |
| Frontend `GET /api/health` | The frontend route can answer a request. | `200`, `{"status":"ok"}` |
| Frontend `GET /api/ready` | The frontend fetches its configured backend's `/api/health` and validates the response. | `200`, `{"status":"ok","frontend":"ok","backend":"ok"}` |
| Backend `GET /api/health` | The FastAPI health handler can answer a request. | `200` JSON containing `status`, `application`, `version`, and a UTC `timestamp`. |

Frontend health and readiness responses use `Cache-Control: no-store`. Readiness runs dynamically and gives its backend request a five-second timeout. It requires a successful HTTP status, a content type containing `application/json`, parseable JSON, and `status` exactly equal to `ok`.

If any of those checks fails, readiness returns `503` with:

```json
{"status":"degraded","frontend":"ok","backend":"unavailable"}
```

That includes connection failure, timeout, an invalid backend URL, an HTTP error, HTML returned instead of JSON, malformed JSON, or a JSON body with another status. The response does not distinguish those causes; use frontend logs and inspect the configured backend address to identify the failure. A working frontend health endpoint can coexist with degraded readiness.

Readiness fetches the backend health endpoint without service-to-service authorization headers. Backend health is exempt from the frontend-token check. Therefore, an `ok` readiness result does not validate `NW_FRONTEND_TOKEN`, `NW_OPERATOR_TOKEN`, or a signed-in operational API request.

The backend health handler does not query Dokploy, Docker, Beszel, the model provider, the database, routes, or application endpoints. Readiness also does not test those systems. Inspect their observed evidence in the authenticated console before reporting that the environment is healthy.

## Run safe public GET checks

These requests need no passphrase, session cookie, or integration credentials. Keep response headers and JSON together; avoid `curl --fail` here so a useful `503` body remains visible.

```sh
curl --silent --show-error --include --max-time 8 \
  https://nightwatch.midhunpm.in/api/health

curl --silent --show-error --include --max-time 8 \
  https://nightwatch.midhunpm.in/api/ready
```

The eight-second curl limit is a caller-side limit, not the readiness handler's five-second backend timeout. If the caller times out, it has not obtained a readiness result.

For a locally running backend, a separate read-only check is:

```sh
curl --silent --show-error --include --max-time 8 \
  http://127.0.0.1:8000/api/health
```

Use the address reachable from the environment making the request. In a frontend container, `127.0.0.1` refers to that container; it is not the separate backend service. See [the service setup](operations.md#dokploy-service-setup) before changing `NW_BACKEND_URL`. Keep the production backend on its private service network.

## Read freshness in the console

After health and readiness, sign in and check the infrastructure world, telemetry source timestamps, domain observations, and a populated incident detail. Do not infer current measurements from the public showcase or its recorded screenshots.

The world service sleeps ten seconds after each observation cycle, refreshes inventory on a separate 60-second cadence, and schedules domain probes on a 30-second cadence. Work duration and integration failures affect actual update timing; these are implementation intervals, not a refresh SLA.

The Beszel adapter treats a container sample as stale when its timestamp is missing or older than 70 seconds. A known project can have unavailable or stale runtime telemetry. Compare the resource's `observed_at`, evidence source timestamps, domain `checked_at`, and snapshot source states; a recently generated snapshot alone does not make every underlying sample fresh.

On restoration, a persisted world snapshot is marked stale with `Restored observations; refreshing live sources`. A failed observation cycle retains the last known view and marks it stale. Check that warning before interpreting a familiar green state as a new measurement.

The console polls data every 30 seconds and also responds to realtime update events. A reconnecting event stream can coexist with working polling. Conversely, an open event stream does not prove that every observation source is healthy. [Architecture](architecture.md#reconciliation-pipeline) explains how the sources are reconciled.

## Report operational outcomes precisely

For a service, distinguish deployment configuration, observed running replicas, container health, telemetry freshness, and public-route reachability. Missing evidence should remain unavailable instead of becoming an assumed success.

For an incident, distinguish detection, collected evidence, hypotheses, an approved plan, recorded execution, and post-action checks. The absence of an incident does not prove the absence of failures; detection thresholds and observation availability affect incident creation.

For general Dokploy actions, `VERIFIED` currently means management API acceptance plus target readback, with a separate deletion path. Public application health remains independent evidence. Deployment and narrow incident-repair workflows have their own verification behavior; inspect the actual recorded check names, status codes, observations, and times. See [the API reference](reference.md#existing-resource-actions).

Implementation references: [frontend health](../frontend/app/api/health/route.ts), [frontend readiness](../frontend/app/api/ready/route.ts), [readiness validation](../frontend/lib/readiness.ts), [backend health](../backend/nightwatch/api/health.py), [world observation](../backend/nightwatch/services/world_service.py), and [Beszel freshness](../backend/nightwatch/adapters/beszel.py).
