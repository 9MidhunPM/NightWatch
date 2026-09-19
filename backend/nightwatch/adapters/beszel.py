from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from nightwatch.models.telemetry import TelemetryPoint, TelemetrySeries
from nightwatch.models.world import HostMetrics


@dataclass(frozen=True)
class BeszelConnection:
    configured: bool
    available: bool
    message: str
    system_id: str | None = None


class BeszelAdapter:
    """Read-only connectivity check for Beszel's PocketBase-backed REST API."""

    def __init__(self, url: str | None, email: str | None, password: str | None, system_id: str | None) -> None:
        self._url = url.rstrip("/") if url else None
        self._email, self._password, self._system_id = email, password, system_id
        self._token: str | None = None
        self._token_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._url and self._email and self._password)

    async def _authenticate(self, client: httpx.AsyncClient, *, refresh: bool = False) -> str:
        if self._token and not refresh and time.monotonic() - self._token_at < 600:
            return self._token
        auth = await client.post(
            "/api/collections/users/auth-with-password",
            json={"identity": self._email, "password": self._password},
        )
        auth.raise_for_status()
        token = str(auth.json().get("token") or "")
        if not token:
            raise httpx.HTTPError("Beszel did not return an access token.")
        self._token, self._token_at = token, time.monotonic()
        return token

    async def _get(
        self, path: str, params: dict[str, str | int | float | bool | None]
    ) -> dict[str, Any]:
        if not self.configured or self._url is None:
            raise httpx.HTTPError("Beszel is not configured.")
        async with httpx.AsyncClient(base_url=self._url, timeout=6.0) as client:
            token = await self._authenticate(client)
            response = await client.get(path, headers={"Authorization": token}, params=params)
            if response.status_code == 401:
                token = await self._authenticate(client, refresh=True)
                response = await client.get(path, headers={"Authorization": token}, params=params)
            response.raise_for_status()
            value = response.json()
            return value if isinstance(value, dict) else {}

    async def connection(self) -> BeszelConnection:
        if not self.configured:
            return BeszelConnection(False, False, "Beszel is not configured. Add a read-only user and hub URL in Dokploy.")
        assert self._url is not None
        try:
            async with httpx.AsyncClient(base_url=self._url, timeout=4.0) as client:
                token = await self._authenticate(client)
                systems = await client.get(
                    "/api/collections/systems/records",
                    headers={"Authorization": token},
                    params={"perPage": 1, "filter": f"id='{self._system_id}'"} if self._system_id else {"perPage": 1},
                )
                systems.raise_for_status()
                items = systems.json().get("items") or []
                if not items:
                    return BeszelConnection(True, False, "The configured Beszel user cannot see the selected system.", self._system_id)
                return BeszelConnection(True, True, "Beszel is connected with read-only access.", str(items[0].get("id") or self._system_id))
        except httpx.HTTPError:
            return BeszelConnection(True, False, "Nightwatch could not reach Beszel with the configured read-only account.", self._system_id)

    async def host_metrics(self) -> HostMetrics | None:
        if not self.configured:
            return None
        try:
            payload = await self._get(
                "/api/collections/systems/records",
                {"perPage": 1, "filter": f"id='{self._system_id}'"} if self._system_id else {"perPage": 1},
            )
        except httpx.HTTPError:
            return None
        items = payload.get("items")
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            return None
        record = items[0]
        raw_info = record.get("info")
        info: dict[str, Any] = dict(raw_info) if isinstance(raw_info, dict) else {}
        memory_total = self._gib(info.get("m") or info.get("memory"))
        memory_used = self._gib(info.get("mu") or info.get("memoryUsed"))
        disk_total = self._gib(info.get("d") or info.get("disk"))
        disk_used = self._gib(info.get("du") or info.get("diskUsed"))
        return HostMetrics(
            cpu_percent=self._number(info.get("cpu")),
            memory_used_bytes=memory_used,
            memory_total_bytes=memory_total,
            memory_percent=self._number(info.get("mp")) or self._percent(memory_used, memory_total),
            disk_used_bytes=disk_used,
            disk_total_bytes=disk_total,
            disk_percent=self._number(info.get("dp")) or self._percent(disk_used, disk_total),
            observed_at=self._datetime(record.get("updated") or record.get("created")) or datetime.now(UTC),
            source="beszel",
        )

    async def history(self, range_name: str, *, container_name: str | None = None) -> TelemetrySeries:
        ranges = {
            "1h": ("1m", timedelta(hours=1)),
            "24h": ("20m", timedelta(hours=24)),
            "7d": ("120m", timedelta(days=7)),
            "30d": ("480m", timedelta(days=30)),
        }
        if range_name not in ranges:
            raise ValueError("Unsupported telemetry range.")
        if not self.configured:
            return TelemetrySeries(range=range_name, available=False, message="Beszel is not configured.")
        record_type, delta = ranges[range_name]
        collection = "container_stats" if container_name else "system_stats"
        since = (datetime.now(UTC) - delta).strftime("%Y-%m-%d %H:%M:%S")
        filters = [f"created > '{since}'", f"type='{record_type}'"]
        if self._system_id:
            filters.insert(0, f"system='{self._system_id}'")
        try:
            payload = await self._get(
                f"/api/collections/{collection}/records",
                {"page": 1, "perPage": 500, "skipTotal": 1, "filter": " && ".join(filters), "fields": "created,stats", "sort": "created"},
            )
        except httpx.HTTPError:
            return TelemetrySeries(range=range_name, available=False, message="Beszel telemetry is unavailable.")
        points: list[TelemetryPoint] = []
        for record in payload.get("items") or []:
            if not isinstance(record, dict):
                continue
            created = self._datetime(record.get("created"))
            stats = record.get("stats")
            if not created:
                continue
            rows = stats if isinstance(stats, list) else [stats]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if container_name and not self._container_matches(row, container_name):
                    continue
                memory_used = self._gib(row.get("mu") or row.get("memoryUsed") or row.get("mem"))
                points.append(TelemetryPoint(
                    observed_at=created,
                    cpu_percent=self._number(row.get("cpu") or row.get("c")),
                    memory_percent=self._number(row.get("mp") or row.get("memoryPercent")),
                    memory_used_bytes=memory_used,
                    disk_percent=self._number(row.get("dp") or row.get("diskPercent")),
                    network_rx_bytes=self._mebibytes(row.get("nr") or row.get("networkRecv")),
                    network_tx_bytes=self._mebibytes(row.get("ns") or row.get("networkSent")),
                ))
        return TelemetrySeries(range=range_name, available=True, points=points, message=None if points else "No matching Beszel samples were found.")

    @staticmethod
    def _container_matches(row: dict[str, Any], name: str) -> bool:
        observed = str(row.get("name") or row.get("n") or row.get("container") or "")
        return observed == name or observed.startswith((name + ".", name + "-"))

    @staticmethod
    def _number(value: object) -> float | None:
        if not isinstance(value, (int, float, str)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _gib(cls, value: object) -> int | None:
        number = cls._number(value)
        return round(number * 1024**3) if number is not None else None

    @classmethod
    def _mebibytes(cls, value: object) -> int | None:
        number = cls._number(value)
        return round(number * 1024**2) if number is not None else None

    @staticmethod
    def _percent(used: int | None, total: int | None) -> float | None:
        return round(used / total * 100, 2) if used is not None and total else None

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
