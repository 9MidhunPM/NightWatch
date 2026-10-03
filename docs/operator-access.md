# Operator access

[← README](../README.md) · [Operations](operations.md) · [Health checks](health-checks.md)

NightWatch has a public project showcase at `/` and a private, single-operator console. The showcase explains the product through an illustrative scene, a representative incident simulation, and recorded screenshots. It does not grant access to current infrastructure observations or operations.

## Sign in and navigate

Open `/login` using the configured frontend address and enter the operator passphrase. The form posts to `/api/session`; a successful response is `200` with `{"ok":true}`, and the browser navigates to `/world`.

The console layout checks the session before rendering World, Overview, Infrastructure, Incidents, Agent, Deployments, Reports, and Settings. A missing or invalid session redirects to `/login`. Login and console pages are marked `noindex, nofollow`; that indexing policy is separate from their session protection.

The browser reads operational data through the authenticated frontend gateway at `/api/backend/`. Integration credentials and service-to-service headers are added on the server. An unauthenticated gateway request returns `401` with `{"message":"Sign in to continue"}`; `/api/events` also returns `401` without a session.

## Session lifetime and sign-out

The `nightwatch_session` cookie contains an HMAC-signed session with an eight-hour expiry. Its cookie settings are:

| Setting | Current behavior |
| --- | --- |
| `HttpOnly` | Enabled |
| `Secure` | Enabled when `NODE_ENV` is `production` |
| `SameSite` | `Strict` |
| `Path` | `/` |
| `Max-Age` | 28,800 seconds |

Ordinary requests do not extend the signed expiry. When an operational API request returns `401`, the client reloads the page; the console layout can then send the operator back to login. A page already open in a browser is not a promise of a still-valid session.

Use **Sign out** in the console sidebar to delete this browser's session cookie and return to `/login`. The session DELETE route checks the request origin. Signing out does not revoke sessions in other browsers or maintain a server-side revocation list.

## Origin and configuration checks

`NW_FRONTEND_ORIGIN` supplies the expected browser origin, defaulting to `http://localhost:3000` when absent. Login, sign-out, and gateway mutations compare normalized URL origins: scheme, hostname, and effective port must agree. For production, use the exact public HTTPS origin consistently. A different development port or HTTP/HTTPS mismatch can reject a request even when the passphrase is correct.

Operator access requires both `NW_DASHBOARD_PASSPHRASE` and `NW_SESSION_SECRET`; the signing secret must contain at least 32 characters. The secret signs sessions and is not the passphrase entered in the form. Keep both in private deployment configuration. The complete environment map is in [Operations](operations.md#configuration-map).

## Diagnose a rejected login

The session POST handler applies origin, attempt-limit, declared-length, configuration, and passphrase checks in that order. Read the response status and message before changing credentials.

| Status | Response message | What to check |
| --- | --- | --- |
| `403` | `Request origin rejected` | Browser origin and `NW_FRONTEND_ORIGIN` agree. |
| `429` | `Too many attempts. Try again in a minute.` | Allow the current one-minute attempt window to expire. |
| `413` | `Request too large` | Declared `Content-Length` is finite and between 1 and 4,096 bytes. Missing, zero, or invalid length also reaches this response. |
| `503` | `Operator access is not configured.` | Passphrase is set and session secret is set with at least 32 characters. |
| `400` | `Invalid request` | The form body could be read and parsed. |
| `401` | `That passphrase is incorrect.` | The supplied passphrase matches the current frontend configuration. |

The normal UI uses an URL-encoded `passphrase` form field, limits the input to 512 characters, and aborts its login request after ten seconds. The handler's 4,096-byte check examines the declared header; it is not a streaming byte counter. The browser also distinguishes non-JSON and malformed JSON replies through its [response reader](../frontend/lib/http.ts).

Attempt limiting is an in-memory map in each frontend process. It uses `x-real-ip` when present and a shared bucket otherwise. Eight requests passing the origin check can be counted within a 60-second window; a successful login clears that bucket. Malformed requests and configuration failures can count because those checks run afterward. An oversized attempt map also returns `429`. Restarts and separate frontend instances do not share this state, and correct `x-real-ip` handling depends on the reverse-proxy configuration. This is not an account-wide lockout or distributed limiter.

## Diagnose a signed-in request

An accepted login and green readiness do not validate the service-to-service token pair. If the console opens but operational requests fail, inspect the actual gateway response and [health-check boundaries](health-checks.md).

| Gateway result | Current meaning |
| --- | --- |
| `401`, `Sign in to continue` | Frontend session is missing or invalid. A backend `401` can also be forwarded, so inspect its response message. |
| `404`, `Unknown endpoint` | Requested path is outside the frontend route allowlist. |
| `403` on a mutation | Request origin was rejected; this frontend response has no JSON body. |
| `413` on a mutation | Streamed request body exceeded 32,768 bytes. This limit differs from the login length check. |
| `502`, `The backend could not be reached. Try again shortly.` | Backend fetch failed, including timeout or a rejected redirect. |

Most gateway fetches have a 45-second timeout; `agent/stream` uses 180 seconds. JSON backend errors can retain their upstream status. A non-JSON reply outside streaming/CSV/204 handling becomes an explanatory JSON error: a nominally successful unexpected reply becomes `502`, while an existing upstream error status is retained. See [the gateway handler](../frontend/app/api/backend/%5B...path%5D/route.ts) for exact exceptions.

## Rotate access without assuming revocation

Changing the dashboard passphrase affects future logins. Existing sessions are validated against the signing secret and expiry, so a passphrase-only change does not revoke them.

Changing `NW_SESSION_SECRET` invalidates sessions signed with the old value once the receiving frontend process uses the new configuration. Apply a consistent secret across frontend instances; mixed configurations can produce inconsistent login results. Verify new login and sign-out behavior after the deployment. The current shared-passphrase model has no per-user roles or individual session revocation.

Implementation references: [session signing](../frontend/lib/session.ts), [session route](../frontend/app/api/session/route.ts), [console layout](../frontend/app/%28console%29/layout.tsx), and [server gateway helpers](../frontend/lib/server.ts).
