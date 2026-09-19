from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ManagedHostResponse(BaseModel):
    id: str
    hostname: str
    operational_state: str
    os: str
    kernel: str
    architecture: str
    uptime_seconds: int
    cpu_count: int
    cpu_percent: float | None
    memory_total_bytes: int
    memory_used_bytes: int
    root_disk_total_bytes: int
    root_disk_used_bytes: int
    load_1m: float | None
    capabilities: list[str]
    last_refreshed_at: datetime
