# Engineering the gap between intent and reality

[← README](../README.md) · [Architecture](architecture.md)

NightWatch’s most demanding work sits between systems that each report a different part of the truth. The implementation evolved through failures in identity matching, upstream API behavior, serialization, and browser rendering. This is the engineering story supported by the code and repository history—not a claim of benchmarked scale or flawless autonomy.

## 1. Making live data belong to the right service

**The challenge.** Inventory records, container replicas, Compose children, and telemetry samples do not arrive with one universal identifier. A project can exist in Dokploy while the telemetry layer appears to have no matching service.

**The response.** World reconciliation combines inventory with Docker identity before matching Beszel observations. Runtime freshness remains explicit, and unavailable measurements are not filled with synthetic values. Domain observations provide another independent perspective on reachability.

**The tradeoff.** An honest unavailable state is less visually satisfying than a green badge, but it is operationally useful. The system must distinguish “not observed” from “observed unhealthy.” Identity reconciliation still depends on the identifiers exposed by integrations.

Source: [`world_service.py`](../backend/nightwatch/services/world_service.py), [`beszel.py`](../backend/nightwatch/adapters/beszel.py).

## 2. Turning “host this” into a workflow

**The challenge.** Creating a blank application is only the beginning of deployment. Repository ownership, branch, Dockerfile location, routing port, domain, and deployment execution all need to agree. An upstream response can also be empty or differ from the JSON shape a client expects.

**The response.** Deployment orchestration lives in a dedicated service with persisted plans, configuration steps, approval, verification, and retry handling. Existing-resource operations have their own typed action plans, target snapshots, and version-bound approvals.

**The tradeoff.** A distributed sequence can partially succeed. Durable plan state and readback help explain that outcome; they do not turn multiple remote calls into an atomic transaction. Operators should inspect the recorded result before retrying.

Source: [`deployment_service.py`](../backend/nightwatch/services/deployment_service.py), [`dokploy.py`](../backend/nightwatch/adapters/dokploy.py).

## 3. Learning that “start” depends on state

**The challenge.** The Dokploy application start path could time out for an idle application without a live service to resume. Blindly repeating the same call did not solve the lifecycle mismatch.

**The response.** After checking the current target, NightWatch translates an approved application start into deployment when Dokploy reports `idle` or `error`. Other states keep the normal operation. The result explains the substitution.

**The tradeoff.** API acceptance plus resource readback validates the management operation, not the health of the application’s public endpoint. Those observations remain separate.

Source: [`dokploy_action_service.py`](../backend/nightwatch/services/dokploy_action_service.py); repository commit `c54893c`.

## 4. Keeping an infrastructure world navigable

**The challenge.** A scene can look compelling and still be a poor tool: circular clustering obscures relationships, unresolved wires look meaningless, and telemetry refreshes can disrupt camera position. Flat cards also need enough vertical space for variable service and domain counts.

**The response.** The frontend uses an explicit node/edge graph, deterministic planar placement, connection-aware relaxation, and graph-derived endpoints. World-scene state and flat-view layout received dedicated changes as the live inventory exposed problems that static mockups did not.

**The tradeoff.** Visual proximity remains a layout decision. It must never be presented as measured latency or physical location.

Source: [`world-layout.ts`](../frontend/lib/world-layout.ts), [`world-scene.tsx`](../frontend/components/world-scene.tsx), [`world-page.tsx`](../frontend/components/world-page.tsx).

## 5. Giving incidents a readable chronology

**The challenge.** A coarse “hours ago” label does not explain an incident. Summary modification time, original detection, evidence collection, and recovery can all occur at different moments.

**The response.** The detailed view exposes persisted timeline events, exact local dates, trigger payloads, evidence, affected resources, and repair/verification history. Latest activity considers recorded events and observations alongside the incident’s update timestamp.

**A concrete lesson.** The initial formatter combined incompatible `Intl.DateTimeFormat` options. Type checking and a successful build did not catch the exception; rendering a real timestamp did. Commit `c0aadf1` replaced the options with explicit date/time fields. That is a useful boundary between static validation and runtime evidence.

Source: [`incident-view.tsx`](../frontend/components/incident-view.tsx), [`incident_service.py`](../backend/nightwatch/services/incident_service.py).

## 6. Making agent cost an architectural concern

**The challenge.** Letting frequent observation cycles trigger broad model investigation creates cost without guaranteeing useful incident records.

**The response.** Continuous monitoring and model investigation are separated. Chat remains on Luna; manual investigation uses a smaller configured model, compact evidence context, a three-tool-call ceiling, a response output limit, and an overall timeout. Incident detection can therefore continue without automatic model work.

**The tradeoff.** Bounded investigation may end with incomplete evidence. The correct result is an explicit limitation or unconfirmed hypothesis, not an artificially confident diagnosis. Limits reduce exposure; they do not establish a measured cost guarantee.

Source: [`config.py`](../backend/nightwatch/config.py), [`investigator.py`](../backend/nightwatch/agents/investigator.py), [`main.py`](../backend/nightwatch/main.py).

## What this project demonstrates

NightWatch brings together asynchronous Python services, persistent workflow modeling, integration-contract handling, agent tool design, and interactive 3D rendering. Its defining engineering principle is that **every operational claim needs a corresponding observation or recorded decision**.

That principle is also the roadmap: stronger end-to-end browser coverage, richer post-action health verification, paginated history, and clearer handling of ambiguous integration identities. These are opportunities for further work, not finished capabilities hidden behind marketing language.
