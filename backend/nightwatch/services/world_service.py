from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.adapters.docker import DockerUnavailableError
from nightwatch.adapters.dokploy import DokployAdapter, DokployError
from nightwatch.adapters.domain_probe import probe_domain
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.world import (
    DomainCheck,
    WorldConnection,
    WorldProject,
    WorldResource,
    WorldSnapshot,
)
from nightwatch.services.docker_service import DockerService
from nightwatch.services.incident_service import IncidentService

logger = logging.getLogger("nightwatch.world")
SERVICE_TYPES = {
    "applications": "application",
    "compose": "compose",
    "postgres": "postgres",
    "mysql": "mysql",
    "mariadb": "mariadb",
    "mongo": "mongo",
    "redis": "redis",
    "libsql": "libsql",
}


def aggregate_health(states: list[str]) -> str:
    if not states:
        return "UNKNOWN"
    for state in ("UNHEALTHY", "DEGRADED", "UNKNOWN", "CHANGING", "STOPPED"):
        if state in states:
            return state
    return "HEALTHY"


class WorldService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        dokploy: DokployAdapter,
        docker: DockerService,
        incidents: IncidentService,
        bus: EventBus,
    ) -> None:
        self.sessions, self.dokploy, self.docker = sessions, dokploy, docker
        self.incidents, self.bus = incidents, bus
        self.current = WorldSnapshot(
            generated_at=datetime.now(UTC), message="Discovering infrastructure"
        )
        self._discovered = 0.0
        self._probed = 0.0
        self._limit = asyncio.Semaphore(4)

    async def restore(self) -> None:
        async with self.sessions() as session:
            value = await session.scalar(
                text("SELECT payload FROM world_state WHERE key='snapshot'")
            )
        if value:
            self.current = WorldSnapshot.model_validate_json(value)
            self.current.stale = True
            self.current.message = "Restored observations; refreshing live sources"

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("World observation cycle failed")
                self.current.stale = True
                self.current.message = "Observation interrupted; showing last known data"
            await asyncio.sleep(10)

    async def tick(self) -> None:
        snapshot = self.current.model_copy(deep=True)
        now = time.monotonic()
        if now - self._discovered >= 60:
            try:
                snapshot.projects = await self.discover()
                snapshot.inventory_at = datetime.now(UTC)
                snapshot.sources["dokploy"] = "available"
                snapshot.stale = False
                snapshot.message = None
            except (DokployError, ValueError, TypeError):
                snapshot.stale = True
                snapshot.sources["dokploy"] = "unavailable"
                snapshot.message = "Dokploy discovery unavailable; showing last known inventory"
            self._discovered = now
        await self.runtime(snapshot)
        if now - self._probed >= 30:
            # Each normalized URL is checked once, even if attached to multiple services.
            checks = {
                check.url: check
                for p in snapshot.projects
                for r in p.resources
                for check in r.domains
            }
            observations = await asyncio.gather(*(self.observe(check) for check in checks.values()))
            by_url = {check.url: check for check in observations}
            for project in snapshot.projects:
                for resource in project.resources:
                    resource.domains = [by_url[check.url] for check in resource.domains]
            self._probed = now
        for project in snapshot.projects:
            for resource in project.resources:
                states = [resource.health]
                states.extend(
                    "HEALTHY" if d.state == "PROTECTED" else d.state for d in resource.domains
                )
                resource.health = aggregate_health(states)
            project.health = aggregate_health([r.health for r in project.resources])
        snapshot.generated_at = datetime.now(UTC)
        snapshot.connections = self.connections(snapshot)
        async with self.sessions() as session:
            await session.execute(
                text(
                    "INSERT INTO world_state(key,payload) VALUES('snapshot',:payload) "
                    "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload"
                ),
                {"payload": snapshot.model_dump_json()},
            )
            await session.commit()
        self.current = snapshot
        await self.bus.publish(
            RealtimeEvent(
                type=EventType.TOPOLOGY_UPDATED,
                payload={"source": "world", "projects": len(snapshot.projects)},
            )
        )

    async def discover(self) -> list[WorldProject]:
        raw = self.dokploy._projects(await self.dokploy._async_request("GET", "/api/project.all"))
        previous = {r.id: r for p in self.current.projects for r in p.resources}
        projects: list[WorldProject] = []
        work: list[tuple[WorldProject, str, str, dict[str, object]]] = []
        compose_definitions: dict[str, dict[str, object]] = {}
        for item in raw:
            project = WorldProject(
                id=str(item["projectId"]), name=str(item.get("name") or "Unnamed project")
            )
            projects.append(project)
            for env in item.get("environments") or []:
                environment = str(env.get("name") or "default")
                project.environments.append(environment)
                for collection, kind in SERVICE_TYPES.items():
                    for service in env.get(collection) or []:
                        work.append((project, environment, kind, service))

        async def detail(
            project: WorldProject, environment: str, kind: str, service: dict[str, object]
        ) -> WorldResource:
            identity = str(service.get(f"{kind}Id") or "")
            resource = WorldResource(
                id=f"dokploy:{kind}:{identity}",
                name=str(service.get("name") or kind),
                kind=kind,
                project_id=project.id,
                environment=environment,
            )
            old = previous.get(resource.id)
            try:
                async with self._limit:
                    data = self.dokploy._data(
                        await self.dokploy._async_request(
                            "GET", f"/api/{kind}.one", params={f"{kind}Id": identity}
                        )
                    )
                if not isinstance(data, dict):
                    raise DokployError("Invalid service detail")
                resource.name = str(data.get("name") or resource.name)
                resource.app_name = str(data.get("appName") or "")
                resource.deployment_state = str(data.get(f"{kind}Status") or "unknown")
                resource.observed_at = datetime.now(UTC)
                if kind == "compose":
                    raw_compose = data.get("composeFile")
                    if isinstance(raw_compose, str) and len(raw_compose) < 2000000:
                        try:
                            parsed = yaml.safe_load(raw_compose)
                            services = parsed.get("services") if isinstance(parsed, dict) else None
                            if isinstance(services, dict):
                                compose_definitions[resource.id] = services
                        except yaml.YAMLError:
                            pass
                domain_rows = data.get("domains") or []
                if kind in {"application", "compose"} and not domain_rows:
                    async with self._limit:
                        domains = self.dokploy._data(
                            await self.dokploy._async_request(
                                "GET",
                                f"/api/domain.by{kind.title()}Id",
                                params={f"{kind}Id": identity},
                            )
                        )
                    domain_rows = domains if isinstance(domains, list) else []
                old_checks = {d.url: d for d in old.domains} if old else {}
                for domain in domain_rows:
                    host = str(domain.get("host") or "").strip().lower()
                    path = str(domain.get("path") or "/")
                    if not host or "*" in host or any(c in host for c in "/@?# "):
                        continue
                    url = f"{'https' if domain.get('https') else 'http'}://{host}{path if path.startswith('/') else '/'}"
                    if url not in {d.url for d in resource.domains}:
                        resource.domains.append(
                            old_checks.get(
                                url, DomainCheck(url=url, target_service=domain.get("serviceName"))
                            )
                        )
            except (DokployError, ValueError, TypeError):
                if old:
                    resource = old.model_copy(deep=True)
                resource.deployment_state = "unknown"
                resource.health = "UNKNOWN"
                resource.observed_at = None
            return resource

        resolved = await asyncio.gather(*(detail(*job) for job in work))
        for (project, _, _, _), resource in zip(work, resolved, strict=True):
            definitions = compose_definitions.get(resource.id, {})
            if definitions:
                for name, definition in definitions.items():
                    if not isinstance(definition, dict):
                        continue
                    child = resource.model_copy(deep=True)
                    child.id, child.name, child.compose_service = (
                        f"{resource.id}:service:{name}",
                        name,
                        name,
                    )
                    dependencies = definition.get("depends_on") or []
                    child.declared_dependencies = (
                        [str(key) for key in dependencies]
                        if isinstance(dependencies, (list, dict))
                        else []
                    )
                    child.domains = [d for d in child.domains if d.target_service == name]
                    old_child = previous.get(child.id)
                    if old_child:
                        old_domains = {d.url: d for d in old_child.domains}
                        child.domains = [old_domains.get(d.url, d) for d in child.domains]
                    project.resources.append(child)
                # Domains without a known Compose service remain visible on the stack.
                unmatched = [d for d in resource.domains if d.target_service not in definitions]
                if unmatched:
                    resource.domains = unmatched
                    project.resources.append(resource)
            else:
                project.resources.append(resource)
        return sorted(projects, key=lambda project: project.name.casefold())

    async def runtime(self, snapshot: WorldSnapshot) -> None:
        try:
            inventory = await self.docker.inventory(publish_event=False)
        except DockerUnavailableError:
            snapshot.sources["docker"] = "unavailable"
            for project in snapshot.projects:
                for resource in project.resources:
                    resource.runtime_state, resource.health = "unknown", "UNKNOWN"
            return
        snapshot.sources["docker"] = "available"
        for project in snapshot.projects:
            for resource in project.resources:
                matches = [
                    c
                    for c in inventory.containers
                    if resource.app_name
                    and (
                        c.compose_project == resource.app_name
                        or c.labels.get("com.docker.swarm.service.name") == resource.app_name
                        or c.name == resource.app_name
                    )
                    and (
                        not resource.compose_service
                        or c.compose_service == resource.compose_service
                    )
                ]
                resource.container_ids = [f"container:{c.id}" for c in matches]
                resource.networks = sorted({n for c in matches for n in c.networks})
                resource.runtime_state = (
                    ", ".join(sorted({c.state for c in matches})) or "not observed"
                )
                if not matches:
                    resource.health = (
                        "CHANGING" if resource.deployment_state == "running" else "UNKNOWN"
                    )
                else:
                    resource.health = aggregate_health(
                        [
                            "UNHEALTHY"
                            if c.health == "unhealthy" or c.state == "dead"
                            else "STOPPED"
                            if c.state == "exited"
                            else "HEALTHY"
                            if c.state == "running"
                            else "DEGRADED"
                            for c in matches
                        ]
                    )

    async def observe(self, previous: DomainCheck) -> DomainCheck:
        async with self._limit:
            current = await probe_domain(previous.url)
        current.incident_id = previous.incident_id
        current.target_service = previous.target_service
        key = f"world:http:{previous.url}"
        if current.state == "UNHEALTHY":
            current.failures = previous.failures + 1
            if current.failures >= 3:
                if not previous.incident_id:
                    incident = await self.incidents.report_failure(
                        key=key,
                        title=f"Domain unavailable: {urlsplit(current.url).hostname}",
                        severity="CRITICAL",
                        trigger={"type": "HTTP_FAILURE", "url": current.url},
                        affected_resource_ids=[f"domain:{urlsplit(current.url).hostname}"],
                        observation_summary=current.message,
                        observation_data=current.model_dump(mode="json"),
                    )
                    current.incident_id = incident.id
            else:
                current.state = "DEGRADED"
                current.message += f" ({current.failures}/3 failed checks)"
        elif current.state in {"HEALTHY", "PROTECTED"}:
            current.successes = previous.successes + 1
            if previous.incident_id:
                if current.successes >= 2:
                    await self.incidents.report_recovery(
                        key, "Endpoint reachable on two consecutive checks"
                    )
                    current.incident_id = None
                else:
                    current.state = "DEGRADED"
                    current.message = "Reachable; waiting for a second recovery check"
        return current

    @staticmethod
    def connections(snapshot: WorldSnapshot) -> list[WorldConnection]:
        edges: list[WorldConnection] = []
        for project in snapshot.projects:
            for resource in project.resources:
                for check in resource.domains:
                    source = f"domain:{urlsplit(check.url).hostname}"
                    edges.append(
                        WorldConnection(
                            id=f"{source}:{resource.id}",
                            source=source,
                            target=resource.id,
                            kind="ROUTES_TO",
                            provenance="Dokploy domain configuration",
                        )
                    )
                for dependency in resource.declared_dependencies:
                    target = next(
                        (
                            r
                            for r in project.resources
                            if r.app_name == resource.app_name and r.compose_service == dependency
                        ),
                        None,
                    )
                    if target:
                        edges.append(
                            WorldConnection(
                                id=f"{resource.id}:depends:{target.id}",
                                source=resource.id,
                                target=target.id,
                                kind="DEPENDS_ON",
                                provenance="Compose depends_on",
                            )
                        )
                for network in resource.networks:
                    edges.append(
                        WorldConnection(
                            id=f"{resource.id}:network:{network}",
                            source=resource.id,
                            target=f"network:{network}",
                            kind="MEMBER_OF",
                            provenance="Docker network membership",
                        )
                    )
        return edges
