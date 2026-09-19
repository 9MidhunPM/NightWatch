from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.adapters.beszel import BeszelContainer
from nightwatch.adapters.docker import DockerUnavailableError
from nightwatch.adapters.dokploy import DokployAdapter, DokployError
from nightwatch.adapters.domain_probe import probe_domain
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.docker_api import DockerContainer
from nightwatch.models.traefik_api import TraefikRoute
from nightwatch.models.world import (
    DeploymentSummary,
    DomainCheck,
    EvidenceStatus,
    HostMetrics,
    ReplicaState,
    ResourceMetrics,
    WorldConnection,
    WorldProject,
    WorldResource,
    WorldSnapshot,
)
from nightwatch.services.beszel_service import BeszelService
from nightwatch.services.docker_service import DockerService
from nightwatch.services.host_service import HostService
from nightwatch.services.incident_service import IncidentService
from nightwatch.services.topology_service import TopologyService

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
        return "UNAVAILABLE"
    known = [state for state in states if state != "UNKNOWN"]
    if not known:
        return "UNKNOWN"
    for state in ("UNHEALTHY", "DEGRADED", "CHANGING", "STOPPED", "UNAVAILABLE"):
        if state in known:
            return state
    return "HEALTHY"


def aggregate_project_health(states: list[str]) -> str:
    if not states:
        return "UNAVAILABLE"
    if all(state in {"UNKNOWN", "UNAVAILABLE"} for state in states):
        return "UNAVAILABLE" if "UNAVAILABLE" in states else "UNKNOWN"
    known = [state for state in states if state not in {"UNKNOWN", "UNAVAILABLE"}]
    for state in ("UNHEALTHY", "DEGRADED", "CHANGING", "STOPPED"):
        if state in known:
            return state
    return "DEGRADED" if len(known) != len(states) else "HEALTHY"


_UNIT_FACTORS = {
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


def parse_bytes(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?i?b)\s*", value, re.IGNORECASE
    )
    if not match:
        return None
    return round(float(match.group(1)) * _UNIT_FACTORS[match.group(2).lower()])


def parse_pair(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, str):
        return None, None
    parts = value.split("/", maxsplit=1)
    return (parse_bytes(parts[0]), parse_bytes(parts[1])) if len(parts) == 2 else (None, None)


def parse_percent(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return float(value.strip().removesuffix("%"))
    except ValueError:
        return None


class WorldService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        dokploy: DokployAdapter,
        docker: DockerService,
        incidents: IncidentService,
        bus: EventBus,
        host: HostService | None = None,
        beszel: BeszelService | None = None,
        topology: TopologyService | None = None,
    ) -> None:
        self.sessions, self.dokploy, self.docker = sessions, dokploy, docker
        self.incidents, self.bus = incidents, bus
        self.host, self.beszel, self.topology = host, beszel, topology
        self.current = WorldSnapshot(
            generated_at=datetime.now(UTC), message="Discovering infrastructure"
        )
        self._discovered = 0.0
        self._probed = 0.0
        self._limit = asyncio.Semaphore(4)
        self._beszel_runtime_state: tuple[bool, bool, int] | None = None
        self._resource_failures: dict[str, int] = {}

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
        if self.host is not None:
            try:
                host = await self.host.get_host(publish_event=False)
                snapshot.host_metrics = HostMetrics(
                    cpu_percent=host.cpu_percent,
                    memory_used_bytes=host.memory_used_bytes,
                    memory_total_bytes=host.memory_total_bytes,
                    memory_percent=round(host.memory_used_bytes / host.memory_total_bytes * 100, 2) if host.memory_total_bytes else None,
                    disk_used_bytes=host.root_disk_used_bytes,
                    disk_total_bytes=host.root_disk_total_bytes,
                    disk_percent=round(host.root_disk_used_bytes / host.root_disk_total_bytes * 100, 2) if host.root_disk_total_bytes else None,
                    load_1m=host.load_1m,
                    observed_at=host.last_refreshed_at,
                    source="host",
                )
                snapshot.sources["host"] = "available"
            except Exception:  # noqa: BLE001 - optional host telemetry cannot stop world discovery
                snapshot.sources["host"] = "unavailable"
        if self.beszel is not None:
            beszel_metrics = await self.beszel.host_metrics()
            if beszel_metrics is not None:
                snapshot.host_metrics = beszel_metrics
                snapshot.sources["beszel"] = "available"
            else:
                snapshot.sources["beszel"] = "unavailable"
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
            project.health = aggregate_project_health([r.health for r in project.resources])
        await self._reconcile_resource_incidents(snapshot)
        observed = [r for p in snapshot.projects for r in p.resources if r.runtime_state != "not observed"]
        total = sum(len(p.resources) for p in snapshot.projects)
        snapshot.coverage = round(len(observed) / total * 100, 1) if total else 100.0
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

    async def _reconcile_resource_incidents(self, snapshot: WorldSnapshot) -> None:
        """Turn repeated Beszel-backed stopped/unhealthy states into visible incidents."""
        for project in snapshot.projects:
            for resource in project.resources:
                key = f"world:resource:{resource.id}"
                if resource.health in {"UNHEALTHY", "STOPPED"}:
                    count = self._resource_failures.get(key, 0) + 1
                    self._resource_failures[key] = count
                    if count >= 3:
                        await self.incidents.report_failure(
                            key=key,
                            title=f"Service unavailable: {resource.name}",
                            severity="CRITICAL",
                            trigger={"type": "BESZEL_RESOURCE_UNHEALTHY", "health": resource.health, "project": project.name},
                            affected_resource_ids=[resource.id],
                            observation_summary=f"Beszel observed {resource.name} as {resource.health.lower()} for {count} consecutive checks.",
                            observation_data={"health": resource.health, "runtime_state": resource.runtime_state, "observed_at": resource.observed_at},
                        )
                elif resource.health == "HEALTHY" and self._resource_failures.pop(key, 0) >= 3:
                    await self.incidents.report_recovery(key, f"Beszel observed {resource.name} healthy again.")

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
                resource.owner = str(data.get("owner")) if data.get("owner") else None
                resource.repository = str(data.get("repository")) if data.get("repository") else None
                resource.branch = str(data.get("branch")) if data.get("branch") else None
                resource.build_type = str(data.get("buildType")) if data.get("buildType") else None
                resource.build_path = str(data.get("buildPath")) if data.get("buildPath") else None
                resource.dockerfile = str(data.get("dockerfile")) if data.get("dockerfile") else None
                resource.image = str(data.get("dockerImage")) if data.get("dockerImage") else None
                resource.auto_deploy = data.get("autoDeploy") if isinstance(data.get("autoDeploy"), bool) else None
                deployments = data.get("deployments") or []
                resource.recent_deployments = []
                for deployment in deployments[:5] if isinstance(deployments, list) else []:
                    if not isinstance(deployment, dict):
                        continue
                    description = str(deployment.get("description") or "")
                    commit_match = re.search(
                        r"Commit:\s*([0-9a-f]{7,40})", description, re.IGNORECASE
                    )
                    resource.recent_deployments.append(
                        DeploymentSummary(
                            id=str(deployment.get("deploymentId") or "unknown"),
                            title=str(deployment.get("title") or "Deployment"),
                            status=str(deployment.get("status") or "unknown"),
                            commit=commit_match.group(1) if commit_match else None,
                            created_at=deployment.get("createdAt"),
                            finished_at=deployment.get("finishedAt"),
                        )
                    )
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
        if self.beszel is None:
            runtime = None
            snapshot.sources["beszel"] = "unavailable"
        else:
            runtime = await self.beszel.containers()
            snapshot.sources["beszel"] = "available" if runtime.available else "unavailable"
            state = (runtime.available, runtime.stale, len(runtime.containers))
            if state != self._beszel_runtime_state:
                logger.info(
                    "Beszel runtime observation changed: available=%s stale=%s containers=%s",
                    *state,
                )
                self._beszel_runtime_state = state
        try:
            inventory = await self.docker.inventory(publish_event=False) if self.docker else None
        except DockerUnavailableError:
            snapshot.sources["docker"] = "unavailable"
            inventory = None
        else:
            snapshot.sources["docker"] = "available" if inventory else "unavailable"
        routes = await self._routes()
        for project in snapshot.projects:
            for resource in project.resources:
                resource.evidence = [
                    EvidenceStatus(source="dokploy", observed_at=resource.observed_at, state="available" if resource.observed_at else "unavailable"),
                    EvidenceStatus(
                        source="beszel",
                        observed_at=runtime.observed_at if runtime else None,
                        state="available" if runtime and runtime.available and not runtime.stale else "unavailable",
                        message=runtime.message if runtime else "Beszel runtime telemetry is unavailable.",
                    ),
                    EvidenceStatus(source="docker", observed_at=inventory.discovered_at if inventory else None, state="available" if inventory else "unavailable"),
                ]
                docker_matches = [
                    c
                    for c in (inventory.containers if inventory else [])
                    if resource.app_name
                    and (
                        c.compose_project == resource.app_name
                        or c.labels.get("com.docker.swarm.service.name") == resource.app_name
                        or c.name == resource.app_name
                        or c.name.startswith(resource.app_name + ".")
                    )
                    and (
                        not resource.compose_service
                        or c.compose_service == resource.compose_service
                    )
                ]
                self._merge_route_domains(resource, docker_matches, routes)
                resource.networks = sorted({network for c in docker_matches for network in c.networks})
                matches = [
                    item
                    for item in (runtime.containers if runtime and runtime.available else [])
                    if self._beszel_matches(resource, item, docker_matches)
                ]
                evidence_message = runtime.message if runtime else "Beszel runtime telemetry is unavailable."
                if runtime and runtime.available:
                    evidence_message = f"Beszel matched {len(matches)} fresh container record(s) through Dokploy and Docker identity."
                resource.evidence[1].message = evidence_message
                resource.container_ids = [f"beszel:{item.id}" for item in matches if item.id]
                if matches and not all(item.stale for item in matches):
                    fresh = [item for item in matches if not item.stale]
                    resource.replicas = ReplicaState(running=len(fresh))
                    resource.runtime_state = f"{len(fresh)} observed replica{'s' if len(fresh) != 1 else ''}"
                    cpu_values = [item.cpu_percent for item in fresh if item.cpu_percent is not None]
                    memory_values = [item.memory_used_bytes for item in fresh if item.memory_used_bytes is not None]
                    network_values = [item.network_bytes for item in fresh if item.network_bytes is not None]
                    resource.metrics = ResourceMetrics(
                        cpu_percent=round(sum(cpu_values), 2) if cpu_values else None,
                        memory_used_bytes=sum(memory_values) if memory_values else None,
                        network_rx_bytes=sum(network_values) if network_values else None,
                        observed_at=max((item.observed_at for item in fresh if item.observed_at), default=None),
                        source="beszel",
                    )
                    resource.health = self._beszel_health(fresh)
                else:
                    resource.replicas = None
                    resource.metrics = None
                    resource.runtime_state = "Beszel has no fresh matching container"
                    resource.health = "UNAVAILABLE"

    @staticmethod
    def _beszel_matches(resource: WorldResource, container: BeszelContainer, docker_matches: Sequence[DockerContainer] = ()) -> bool:
        if not resource.app_name or not container.name:
            return False
        name = container.name.lstrip("/").casefold()
        for docker in docker_matches:
            docker_name = str(getattr(docker, "name", "")).lstrip("/").casefold()
            docker_id = str(getattr(docker, "id", "")).casefold()
            if name == docker_name or (container.id and docker_id.startswith(container.id.casefold())):
                return True
        app_name = resource.app_name.casefold()
        prefixes = [
            f"{app_name}-{resource.compose_service.casefold()}"
            if resource.compose_service
            else app_name
        ]
        return any(name == prefix or name.startswith((prefix + ".", prefix + "-", prefix + "_")) for prefix in prefixes)

    async def _routes(self) -> list[TraefikRoute]:
        if self.topology is None:
            return []
        try:
            return list(await self.topology.traefik_routes())
        except Exception:
            logger.info("Traefik route observation unavailable", exc_info=True)
            return []

    @staticmethod
    def _merge_route_domains(resource: WorldResource, docker_matches: Sequence[DockerContainer], routes: Sequence[TraefikRoute]) -> None:
        container_ids = {str(getattr(container, "id", "")) for container in docker_matches}
        container_names = {str(getattr(container, "name", "")).lstrip("/") for container in docker_matches}
        known = {check.url for check in resource.domains}
        for route in routes:
            if str(getattr(route, "container_id", "")) not in container_ids and str(getattr(route, "container_name", "")).lstrip("/") not in container_names:
                continue
            for host in getattr(route, "domains", []):
                url = f"https://{str(host).strip().lower()}/"
                if host and url not in known:
                    resource.domains.append(DomainCheck(url=url, target_service=getattr(route, "service_name", None)))
                    known.add(url)

    @staticmethod
    def _beszel_health(containers: list[BeszelContainer]) -> str:
        statuses = [item.status.casefold() for item in containers]
        if any(item.health == 3 for item in containers):
            return "UNHEALTHY"
        if any("dead" in status or "exited" in status or "stopped" in status for status in statuses):
            return "STOPPED"
        if any(item.health == 1 or "starting" in status or "restarting" in status for item, status in zip(containers, statuses, strict=True)):
            return "CHANGING"
        if any("up" in status or "running" in status for status in statuses):
            return "HEALTHY"
        return "DEGRADED"

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
