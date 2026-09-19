from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import cast

from nightwatch.adapters.docker import DockerUnavailableError
from nightwatch.adapters.dokploy import DokployAdapter
from nightwatch.adapters.traefik import TraefikAdapter
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.docker_api import DockerContainer, DockerInventory
from nightwatch.models.topology_api import (
    HealthState,
    InfrastructureEdge,
    InfrastructureNode,
    NodeType,
    TopologySnapshot,
)
from nightwatch.models.traefik_api import TraefikRoute
from nightwatch.services.docker_service import DockerService
from nightwatch.services.host_service import LOCAL_HOST_ID, HostService
from nightwatch.services.incident_service import IncidentService


class TopologyService:
    def __init__(
        self,
        host_service: HostService,
        docker_service: DockerService,
        traefik_adapter: TraefikAdapter,
        event_bus: EventBus,
        incident_service: IncidentService,
        dokploy_adapter: DokployAdapter,
    ) -> None:
        self._host_service = host_service
        self._docker_service = docker_service
        self._traefik_adapter = traefik_adapter
        self._event_bus = event_bus
        self._incident_service = incident_service
        self._dokploy_adapter = dokploy_adapter
        self._cached_snapshot: TopologySnapshot | None = None
        self._cached_at = 0.0
        self._snapshot_lock = asyncio.Lock()

    async def snapshot(self, publish_event: bool = False) -> TopologySnapshot:
        if not publish_event and self._cached_snapshot is not None and time.monotonic() - self._cached_at < 10:
            return self._cached_snapshot
        async with self._snapshot_lock:
            if not publish_event and self._cached_snapshot is not None and time.monotonic() - self._cached_at < 10:
                return self._cached_snapshot
            return await self._snapshot_uncached(publish_event=publish_event)

    async def _snapshot_uncached(self, *, publish_event: bool) -> TopologySnapshot:
        host = await self._host_service.get_host(publish_event=False)
        host_node = InfrastructureNode(
            id=f"host:{LOCAL_HOST_ID}",
            type="HOST",
            label=host.hostname,
            health="HEALTHY",
            detail=host.os,
            attributes={"architecture": host.architecture},
        )
        try:
            inventory = await self._docker_service.inventory(publish_event=False)
        except DockerUnavailableError:
            snapshot = TopologySnapshot(
                available=False,
                message="Docker is unavailable to the Nightwatch backend.",
                generated_at=datetime.now(UTC),
                nodes=[host_node],
                sources=["host"],
            )
        else:
            routes = await asyncio.to_thread(self._traefik_adapter.discover)
            project_names = await asyncio.to_thread(self._dokploy_adapter.service_project_names)
            snapshot = await self._incident_service.overlay_health(
                self._build(host_node, inventory, routes, project_names)
            )
        self._cached_snapshot = snapshot
        self._cached_at = time.monotonic()
        if publish_event:
            await self._event_bus.publish(
                RealtimeEvent(
                    type=EventType.TOPOLOGY_UPDATED,
                    payload={"node_count": len(snapshot.nodes), "edge_count": len(snapshot.edges)},
                )
            )
        return snapshot

    async def traefik_routes(self) -> list[TraefikRoute]:
        return await asyncio.to_thread(self._traefik_adapter.discover)

    async def related_slice(self, resource_ids: list[str]) -> TopologySnapshot:
        snapshot = await self.snapshot(publish_event=False)
        related = set(resource_ids)
        for edge in snapshot.edges:
            if edge.id in related or edge.source in related or edge.target in related:
                related.update({edge.id, edge.source, edge.target})
        return snapshot.model_copy(
            update={
                "nodes": [node for node in snapshot.nodes if node.id in related],
                "edges": [
                    edge
                    for edge in snapshot.edges
                    if edge.id in related or (edge.source in related and edge.target in related)
                ],
            }
        )

    @staticmethod
    def _build(
        host: InfrastructureNode,
        inventory: DockerInventory,
        routes: list[TraefikRoute],
        project_names: dict[str, str] | None = None,
    ) -> TopologySnapshot:
        project_names = project_names or {}
        nodes: list[InfrastructureNode] = [host]
        edges: list[InfrastructureEdge] = []
        container_ids: dict[str, str] = {}
        for container in inventory.containers:
            node_id = f"container:{container.id}"
            container_ids[container.id] = node_id
            nodes.append(TopologyService._container_node(node_id, container, project_names))
            edges.append(
                InfrastructureEdge(
                    id=f"{node_id}:runs-on",
                    source=node_id,
                    target=host.id,
                    type="RUNS_ON",
                    health="HEALTHY",
                    provenance="docker_container",
                )
            )
        for network in inventory.networks:
            network_id = f"network:{network.id}"
            nodes.append(
                InfrastructureNode(
                    id=network_id,
                    type="NETWORK",
                    label=network.name,
                    health="UNKNOWN",
                    detail=network.driver,
                    attributes={"internal": str(network.internal).lower()},
                )
            )
            for member in network.containers:
                if member.id in container_ids:
                    edges.append(
                        InfrastructureEdge(
                            id=f"{container_ids[member.id]}:member:{network_id}",
                            source=container_ids[member.id],
                            target=network_id,
                            type="MEMBER_OF",
                            provenance="docker_network",
                        )
                    )
        if routes:
            nodes.append(
                InfrastructureNode(
                    id="internet",
                    type="INTERNET",
                    label="Internet",
                    health="HEALTHY",
                    detail="External traffic",
                )
            )
        proxy_ids = [node.id for node in nodes if node.type == "REVERSE_PROXY"]
        proxy_id = proxy_ids[0] if proxy_ids else None
        for route in routes:
            route_id = f"route:{route.id}"
            nodes.append(
                InfrastructureNode(
                    id=route_id,
                    type="ROUTE",
                    label=route.router_name,
                    health="HEALTHY",
                    detail=route.rule,
                    attributes={
                        "target_port": str(route.target_port or ""),
                        "service": route.service_name or "",
                    },
                )
            )
            for domain in route.domains:
                domain_id = f"domain:{domain}"
                if not any(node.id == domain_id for node in nodes):
                    nodes.append(
                        InfrastructureNode(
                            id=domain_id,
                            type="DOMAIN",
                            label=domain,
                            health="HEALTHY",
                            detail="Traefik Host rule",
                        )
                    )
                    edges.append(
                        InfrastructureEdge(
                            id=f"internet:{domain_id}",
                            source="internet",
                            target=domain_id,
                            type="ROUTES_TO",
                            health="HEALTHY",
                            provenance="traefik_router",
                        )
                    )
                edges.append(
                    InfrastructureEdge(
                        id=f"{domain_id}:{route_id}",
                        source=domain_id,
                        target=route_id,
                        type="ROUTES_TO",
                        health="HEALTHY",
                        provenance="traefik_router",
                        detail=route.rule,
                    )
                )
            if proxy_id:
                edges.append(
                    InfrastructureEdge(
                        id=f"{route_id}:{proxy_id}",
                        source=route_id,
                        target=proxy_id,
                        type="ROUTES_TO",
                        health="HEALTHY",
                        provenance="traefik_router",
                    )
                )
                target_id = container_ids.get(route.container_id)
                if target_id:
                    edges.append(
                        InfrastructureEdge(
                            id=f"{proxy_id}:{target_id}:{route.router_name}",
                            source=proxy_id,
                            target=target_id,
                            type="ROUTES_TO",
                            health="HEALTHY",
                            provenance="traefik_router",
                            detail=f"port {route.target_port}" if route.target_port else None,
                        )
                    )
        sources = ["host", "docker", "traefik_labels"] if routes else ["host", "docker"]
        if project_names:
            sources.append("dokploy_projects")
        return TopologySnapshot(
            available=True,
            generated_at=inventory.discovered_at,
            nodes=nodes,
            edges=edges,
            sources=sources,
        )

    @staticmethod
    def _container_node(node_id: str, container: DockerContainer, project_names: dict[str, str]) -> InfrastructureNode:
        node_type = cast(
            NodeType,
            container.resource_type if container.resource_type != "CONTAINER" else "SERVICE",
        )
        return InfrastructureNode(
            id=node_id,
            type=node_type,
            label=container.name,
            health=cast(HealthState, TopologyService._health(container)),
            detail=container.image,
            protected=(
                "nightwatch" in container.name.lower() or container.resource_type == "REVERSE_PROXY"
            ),
            attributes={
                "image": container.image,
                "state": container.state,
                "health": container.health or "unknown",
                "ports": ", ".join(port.internal for port in container.ports),
                "networks": ", ".join(container.networks),
                "compose_project": container.compose_project or "",
                "project_name": project_names.get(container.compose_project or "")
                or project_names.get(container.compose_service or "")
                or "",
                "compose_service": container.compose_service or "",
                "restart_count": str(container.restart_count),
            },
        )

    @staticmethod
    def _health(container: DockerContainer) -> str:
        if container.health == "unhealthy" or container.state in {"exited", "dead"}:
            return "UNHEALTHY"
        if container.state == "running":
            return "HEALTHY"
        if container.state in {"restarting", "paused"}:
            return "DEGRADED"
        return "UNKNOWN"
