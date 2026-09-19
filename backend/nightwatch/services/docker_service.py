from __future__ import annotations

import asyncio

from nightwatch.adapters.docker import DockerAdapter, DockerUnavailableError
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.docker_api import (
    DockerContainer,
    DockerInventory,
    DockerNetwork,
    DockerStatus,
)
from nightwatch.models.operations_api import ContainerUsage


class DockerService:
    def __init__(self, adapter: DockerAdapter, event_bus: EventBus) -> None:
        self._adapter = adapter
        self._event_bus = event_bus

    async def inventory(self, publish_event: bool = True) -> DockerInventory:
        inventory = await asyncio.to_thread(self._adapter.discover)
        if publish_event:
            await self._event_bus.publish(
                RealtimeEvent(
                    type=EventType.DOCKER_INVENTORY_UPDATED,
                    payload={"container_count": len(inventory.containers)},
                )
            )
        return inventory

    async def status(self) -> DockerStatus:
        try:
            inventory = await self.inventory(publish_event=False)
        except DockerUnavailableError:
            from datetime import UTC, datetime

            return DockerStatus(
                available=False,
                message="Docker is unavailable to the Nightwatch backend.",
                discovered_at=datetime.now(UTC),
            )
        return DockerStatus(
            available=True,
            discovered_at=inventory.discovered_at,
            container_count=len(inventory.containers),
            running_count=sum(container.state == "running" for container in inventory.containers),
            unhealthy_count=sum(
                container.health == "unhealthy" for container in inventory.containers
            ),
        )

    async def containers(self) -> list[DockerContainer]:
        # The resources page polls this endpoint for a fast initial render.
        # Publishing an inventory event for every browser poll creates needless
        # websocket traffic and competes with the metrics request.
        return (await self.inventory(publish_event=False)).containers

    async def container(self, container_id: str) -> DockerContainer | None:
        return next(
            (item for item in (await self.inventory()).containers if item.id == container_id),
            None,
        )

    async def networks(self) -> list[DockerNetwork]:
        return (await self.inventory()).networks

    async def logs(self, container_id: str, tail: int = 100) -> list[str]:
        return await asyncio.to_thread(self._adapter.logs, container_id, tail)

    async def usage(self) -> list[ContainerUsage]:
        return await asyncio.to_thread(self._adapter.usage)
