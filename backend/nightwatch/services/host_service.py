from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.adapters.host import LocalHostAdapter
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.host_api import ManagedHostResponse
from nightwatch.models.server import Server, utc_now

LOCAL_HOST_ID = "local-host"


class HostService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_bus: EventBus,
        adapter: LocalHostAdapter,
        environment: str,
    ) -> None:
        self._session_factory = session_factory
        self._event_bus = event_bus
        self._adapter = adapter
        self._environment = environment

    async def refresh(self, publish_event: bool = True) -> ManagedHostResponse:
        snapshot = self._adapter.inspect()
        async with self._session_factory() as session:
            host = await session.get(Server, LOCAL_HOST_ID)
            if host is None:
                host = Server(id=LOCAL_HOST_ID, name="Managed Host", endpoint="local://host")
                session.add(host)
            host.name = "Managed Host"
            host.endpoint = "local://host"
            host.hostname = snapshot.hostname
            host.connection_status = "HEALTHY"
            host.environment = "LIVE" if self._environment == "production" else "LOCAL"
            host.capabilities = snapshot.capabilities
            host.os_name = snapshot.os_name
            host.kernel = snapshot.kernel
            host.architecture = snapshot.architecture
            host.uptime_seconds = snapshot.uptime_seconds
            host.cpu_count = snapshot.cpu_count
            host.cpu_percent = snapshot.cpu_percent
            host.memory_total_bytes = snapshot.memory_total_bytes
            host.memory_used_bytes = snapshot.memory_used_bytes
            host.root_disk_total_bytes = snapshot.root_disk_total_bytes
            host.root_disk_used_bytes = snapshot.root_disk_used_bytes
            host.load_1m = snapshot.load_1m
            host.last_seen_at = utc_now()
            await session.commit()
            await session.refresh(host)
            response = self._serialize(host)
        if publish_event:
            await self._event_bus.publish(
                RealtimeEvent(
                    type=EventType.HOST_UPDATED,
                    server_id=LOCAL_HOST_ID,
                    payload={"hostname": response.hostname},
                )
            )
        return response

    async def get_host(self, publish_event: bool = False) -> ManagedHostResponse:
        """Read current host data without turning every API read into a realtime event."""
        return await self.refresh(publish_event=publish_event)

    @staticmethod
    def _serialize(host: Server) -> ManagedHostResponse:
        return ManagedHostResponse(
            id=host.id,
            hostname=host.hostname or "unknown",
            operational_state=host.connection_status,
            os=host.os_name or "Unknown Linux",
            kernel=host.kernel or "unknown",
            architecture=host.architecture or "unknown",
            uptime_seconds=host.uptime_seconds or 0,
            cpu_count=host.cpu_count or 0,
            cpu_percent=host.cpu_percent,
            memory_total_bytes=host.memory_total_bytes or 0,
            memory_used_bytes=host.memory_used_bytes or 0,
            root_disk_total_bytes=host.root_disk_total_bytes or 0,
            root_disk_used_bytes=host.root_disk_used_bytes or 0,
            load_1m=host.load_1m,
            capabilities=host.capabilities or [],
            last_refreshed_at=host.last_seen_at or utc_now(),
        )
