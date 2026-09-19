from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TelemetryPoint(BaseModel):
    observed_at: datetime
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_bytes: int | None = None
    disk_percent: float | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None


class TelemetrySeries(BaseModel):
    source: str = "beszel"
    available: bool = False
    stale: bool = False
    message: str | None = None
    resource_id: str | None = None
    range: str
    points: list[TelemetryPoint] = Field(default_factory=list)
