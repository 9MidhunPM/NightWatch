from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from nightwatch.adapters.docker import DockerUnavailableError
from nightwatch.adapters.http import probe_http
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.docker_api import DockerContainer
from nightwatch.services.docker_service import DockerService
from nightwatch.services.incident_service import IncidentService
from nightwatch.services.topology_service import TopologyService

if TYPE_CHECKING:
    from nightwatch.agents.investigator import InvestigatorService

logger = logging.getLogger("nightwatch.monitoring")


class MonitoringService:
    def __init__(
        self,
        docker_service: DockerService,
        topology_service: TopologyService,
        incident_service: IncidentService,
        event_bus: EventBus,
        *,
        demo_url: str | None,
        timeout_seconds: float,
        failure_threshold: int,
        investigator_service: InvestigatorService | None = None,
    ) -> None:
        self._docker_service = docker_service
        self._topology_service = topology_service
        self._incident_service = incident_service
        self._event_bus = event_bus
        self._demo_url = demo_url
        self._timeout_seconds = timeout_seconds
        self._failure_threshold = failure_threshold
        self._investigator_service = investigator_service
        self._failures: dict[str, int] = {}

    async def run_forever(self, interval_seconds: float) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("monitoring cycle failed", extra={"component": "monitoring"})
            await asyncio.sleep(interval_seconds)

    async def run_once(self) -> None:
        try:
            inventory = await self._docker_service.inventory(publish_event=False)
        except DockerUnavailableError:
            inventory = None
        if inventory:
            for container in inventory.containers:
                await self._check_container(container)
        if self._demo_url:
            await self._check_http(self._demo_url)

    async def _check_container(self, container: DockerContainer) -> None:
        unhealthy = container.health == "unhealthy" or container.state in {
            "exited",
            "dead",
            "restarting",
        }
        key = f"container:{container.id}"
        if not unhealthy:
            await self._success(key, f"Container {container.name} is healthy again.")
            return
        await self._failure(
            key=key,
            title=f"Container unhealthy: {container.name}",
            severity="CRITICAL",
            trigger={
                "type": "CONTAINER_UNHEALTHY",
                "state": container.state,
                "health": container.health,
            },
            affected_resource_ids=[key],
            summary=f"Container {container.name} is {container.state} ({container.health or 'no healthcheck'}).",
            data={"state": container.state, "health": container.health or "unknown"},
        )

    async def _check_http(self, url: str) -> None:
        result = await probe_http(url, self._timeout_seconds)
        key = f"http:{url}"
        if result.reachable:
            await self._success(key, f"Public endpoint recovered: {url}")
            return
        affected = await self._route_resources(url)
        await self._failure(
            key=key,
            title=f"Public route unavailable: {urlparse(url).hostname or url}",
            severity="CRITICAL",
            trigger={
                "type": "HTTP_FAILURE",
                "url": url,
                "expected_status": 200,
                "actual_status": result.status_code,
                "error_type": result.error_type,
            },
            affected_resource_ids=affected,
            summary=f"Public endpoint returned {result.status_code or result.error_type or 'an unknown error'}.",
            data={
                "url": url,
                "status_code": result.status_code or 0,
                "latency_ms": result.latency_ms or 0,
                "error_type": result.error_type or "HTTP_ERROR",
            },
        )

    async def _failure(
        self,
        *,
        key: str,
        title: str,
        severity: str,
        trigger: dict[str, object],
        affected_resource_ids: list[str],
        summary: str,
        data: dict[str, object],
    ) -> None:
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count < self._failure_threshold:
            return
        incident = await self._incident_service.report_failure(
            key=key,
            title=title,
            severity=severity,
            trigger=trigger,
            affected_resource_ids=affected_resource_ids,
            observation_summary=summary,
            observation_data=data,
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.HEALTH_STATE_CHANGED,
                incident_id=incident.id,
                resource_id=affected_resource_ids[0] if affected_resource_ids else None,
                payload={"state": "UNHEALTHY", "failure_count": count},
            )
        )
        if count == self._failure_threshold and self._investigator_service:
            self._investigator_service.start(incident.id)

    async def _success(self, key: str, summary: str) -> None:
        if self._failures.pop(key, 0) >= self._failure_threshold:
            incident = await self._incident_service.report_recovery(key, summary)
            if incident:
                await self._event_bus.publish(
                    RealtimeEvent(
                        type=EventType.HEALTH_STATE_CHANGED,
                        incident_id=incident.id,
                        resource_id=incident.affected_resource_ids[0]
                        if incident.affected_resource_ids
                        else None,
                        payload={"state": "HEALTHY"},
                    )
                )

    async def _route_resources(self, url: str) -> list[str]:
        hostname = urlparse(url).hostname
        if not hostname:
            return [f"url:{url}"]
        topology = await self._topology_service.snapshot(publish_event=False)
        domain_id = f"domain:{hostname}"
        if not any(node.id == domain_id for node in topology.nodes):
            return [f"url:{url}"]
        route_ids = {edge.target for edge in topology.edges if edge.source == domain_id}
        edge_ids = [
            edge.id
            for edge in topology.edges
            if edge.source == domain_id or edge.source in route_ids
        ]
        return [domain_id, *sorted(route_ids), *sorted(edge_ids)]
