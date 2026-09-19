"""Bounded public HTTP observations with DNS pinning, including every redirect."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from nightwatch.models.world import DomainCheck


def public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not ip.is_multicast


async def _request(url: str) -> tuple[int, str | None]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Unsupported endpoint")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Only public HTTP and HTTPS ports are monitored")
    host = parsed.hostname.encode("idna").decode("ascii")
    addresses = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not public_address(str(item[4][0])) for item in addresses):
        raise ValueError("Non-public destination blocked")
    # Connect to the validated address, not the hostname, to prevent DNS rebinding.
    address = str(addresses[0][4][0])
    tls = ssl.create_default_context() if parsed.scheme == "https" else None
    reader, writer = await asyncio.open_connection(
        address, port, ssl=tls, server_hostname=host if tls else None, limit=32768
    )
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        if any(char in path + host for char in ("\r", "\n", " ")):
            raise ValueError("Invalid request target")
        writer.write(
            (
                f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                "User-Agent: NightWatch/1.0\r\nAccept: */*\r\nConnection: close\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        headers = (await reader.readuntil(b"\r\n\r\n")).decode("latin1")
        status = int(headers.split("\r\n", 1)[0].split()[1])
        location = next(
            (
                line.split(":", 1)[1].strip()
                for line in headers.split("\r\n")
                if line.lower().startswith("location:")
            ),
            None,
        )
        return status, location
    finally:
        writer.close()
        # Do not wait for an untrusted peer's TLS shutdown.


async def probe_domain(url: str) -> DomainCheck:
    start = time.monotonic()
    result = DomainCheck(url=url, checked_at=datetime.now(UTC))
    try:
        async with asyncio.timeout(3):
            target = url
            for _ in range(4):
                code, redirect = await _request(target)
                result.status_code = code
                if code in {301, 302, 303, 307, 308} and redirect:
                    target = urljoin(target, redirect)
                    continue
                if 200 <= code < 400:
                    result.state, result.message = "HEALTHY", "Endpoint reachable"
                elif code in {401, 403}:
                    result.state, result.message = "PROTECTED", "Reachable; authentication required"
                elif code < 500:
                    result.state, result.message = "DEGRADED", f"Endpoint returned HTTP {code}"
                else:
                    result.state, result.message = "UNHEALTHY", f"Endpoint returned HTTP {code}"
                break
            else:
                result.state, result.message = "DEGRADED", "Redirect limit reached"
    except ValueError:
        result.state, result.message = (
            "UNKNOWN",
            "Endpoint is not an eligible public HTTP(S) destination",
        )
    except (
        OSError,
        TimeoutError,
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
        IndexError,
    ):
        result.state, result.message = "UNHEALTHY", "DNS, TLS, connection, or timeout failure"
    result.latency_ms = round((time.monotonic() - start) * 1000)
    return result
