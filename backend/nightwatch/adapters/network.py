from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime
from time import perf_counter

from pydantic import BaseModel


class TcpProbeResult(BaseModel):
    reachable: bool
    latency_ms: int | None = None
    error_type: str | None = None
    timestamp: datetime


async def probe_tcp(host: str, port: int, timeout_seconds: float) -> TcpProbeResult:
    started = perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout_seconds)
        writer.close()
        await writer.wait_closed()
        return TcpProbeResult(
            reachable=True,
            latency_ms=round((perf_counter() - started) * 1000),
            timestamp=datetime.now(UTC),
        )
    except TimeoutError:
        error = "TIMEOUT"
    except socket.gaierror:
        error = "DNS_ERROR"
    except OSError:
        error = "CONNECTION_REFUSED"
    return TcpProbeResult(
        reachable=False,
        latency_ms=round((perf_counter() - started) * 1000),
        error_type=error,
        timestamp=datetime.now(UTC),
    )


async def resolve_dns(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(item[4][0]) for item in infos})
