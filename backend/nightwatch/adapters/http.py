from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

import httpx
from pydantic import BaseModel


class HttpProbeResult(BaseModel):
    reachable: bool
    status_code: int | None = None
    latency_ms: int | None = None
    error_type: str | None = None
    timestamp: datetime


async def probe_http(url: str, timeout_seconds: float) -> HttpProbeResult:
    started = perf_counter()
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout_seconds) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        return _failure("TIMEOUT", started)
    except httpx.ConnectError as exc:
        return _failure(_connection_error(exc), started)
    except httpx.TransportError:
        return _failure("UNKNOWN", started)
    return HttpProbeResult(
        reachable=response.is_success,
        status_code=response.status_code,
        latency_ms=round((perf_counter() - started) * 1000),
        error_type=None if response.is_success else "HTTP_ERROR",
        timestamp=datetime.now(UTC),
    )


def _failure(error_type: str, started: float) -> HttpProbeResult:
    return HttpProbeResult(
        reachable=False,
        latency_ms=round((perf_counter() - started) * 1000),
        error_type=error_type,
        timestamp=datetime.now(UTC),
    )


def _connection_error(exc: httpx.ConnectError) -> str:
    message = str(exc).lower()
    if "name or service" in message or "nodename" in message:
        return "DNS_ERROR"
    if "refused" in message:
        return "CONNECTION_REFUSED"
    if "ssl" in message or "tls" in message:
        return "TLS_ERROR"
    return "CONNECTION_REFUSED"
