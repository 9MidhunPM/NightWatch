from __future__ import annotations

from nightwatch.adapters.beszel import BeszelAdapter, BeszelConnection
from nightwatch.models.telemetry import TelemetrySeries
from nightwatch.models.world import HostMetrics


class BeszelService:
    def __init__(self, adapter: BeszelAdapter) -> None:
        self._adapter = adapter

    async def connection(self) -> BeszelConnection:
        return await self._adapter.connection()

    async def host_metrics(self) -> HostMetrics | None:
        return await self._adapter.host_metrics()

    async def history(self, range_name: str, *, container_name: str | None = None) -> TelemetrySeries:
        return await self._adapter.history(range_name, container_name=container_name)
