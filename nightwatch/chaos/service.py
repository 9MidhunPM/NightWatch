from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Protocol

from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.remediation.execution import RepairExecutionError


class DemoRouteSource(Protocol):
    path: Path | None
    service: str | None

    def read_port(self, field: str) -> str: ...
    def patch_port(self, field: str, expected: str, replacement: str) -> None: ...
    def redeploy(self) -> None: ...


class ChaosService:
    """Bounded fault injection for the one explicitly configured demo route."""

    def __init__(self, source: DemoRouteSource, events: EventBus, expected_port: int | None) -> None:
        self._source = source
        self._events = events
        self._expected_port = str(expected_port) if expected_port is not None else None
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return self._expected_port is not None and self._source.path is not None and self._source.service is not None

    async def inject_route_mismatch(self) -> None:
        if not self.available:
            raise RepairExecutionError("CHAOS_UNAVAILABLE", "The disposable demo route is not configured.")
        async with self._lock:
            assert self._expected_port is not None
            current = self._source.read_port(self._route_field())
            if current != self._expected_port:
                raise RepairExecutionError("CURRENT_STATE_MISMATCH", "Reset the demo before injecting another fault.")
            # Port 9 is deliberately non-serving. It is an exact, reversible route-only fault.
            await self._replace_port(current, "9")
        await self._events.publish(RealtimeEvent(type=EventType.CHAOS_INJECTED, payload={"scenario": "ROUTE_MISMATCH"}))

    async def reset(self) -> None:
        if not self.available:
            raise RepairExecutionError("CHAOS_UNAVAILABLE", "The disposable demo route is not configured.")
        async with self._lock:
            assert self._expected_port is not None
            current = self._source.read_port(self._route_field())
            if current != self._expected_port:
                await self._replace_port(current, self._expected_port)
        await self._events.publish(RealtimeEvent(type=EventType.CHAOS_RESET, payload={"scenario": "ROUTE_MISMATCH"}))

    def status(self) -> dict[str, object]:
        current_port: str | None = None
        state = "UNAVAILABLE"
        reason: str | None = None
        if self.available:
            try:
                current_port = self._source.read_port(self._route_field())
                state = "HEALTHY" if current_port == self._expected_port else "FAULT_INJECTED"
            except RepairExecutionError as exc:
                state = "ERROR"
                reason = str(exc)
        return {
            "available": self.available,
            "scenarios": ["ROUTE_MISMATCH"] if self.available else [],
            "message": "Only the explicitly flagged disposable demo route can be changed.",
            "state": state,
            "current_port": current_port,
            "expected_port": self._expected_port,
            "reason": reason,
            "actions": {
                "inject_route_mismatch": state == "HEALTHY",
                "reset": state == "FAULT_INJECTED",
            },
        }

    async def _replace_port(self, current: str, replacement: str) -> None:
        field = self._route_field()
        patched = False
        try:
            self._source.patch_port(field, current, replacement)
            patched = True
            await asyncio.to_thread(self._source.redeploy)
        except (OSError, subprocess.SubprocessError, RepairExecutionError) as exc:
            if patched:
                await self._restore(field, replacement, current)
            raise RepairExecutionError("CHAOS_FAILED", "The disposable demo fault could not be applied.") from exc

    async def _restore(self, field: str, current: str, expected: str) -> None:
        try:
            self._source.patch_port(field, current, expected)
            await asyncio.to_thread(self._source.redeploy)
        except (OSError, subprocess.SubprocessError, RepairExecutionError):
            # The caller receives an explicit failure; do not imply the reset succeeded.
            return

    def _route_field(self) -> str:
        if not self._source.service:
            raise RepairExecutionError("CHAOS_UNAVAILABLE", "The disposable demo route is not configured.")
        return "traefik.http.services.nightwatch-demo.loadbalancer.server.port"
