from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from nightwatch.adapters.docker import DockerAdapter
from nightwatch.adapters.traefik import TraefikAdapter


@dataclass(frozen=True)
class HostSnapshot:
    hostname: str
    os_name: str
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


class LocalHostAdapter:
    def __init__(self, docker: DockerAdapter | None = None) -> None:
        self._previous_cpu_times: tuple[int, int] | None = None
        self._docker = docker or DockerAdapter()

    def inspect(self) -> HostSnapshot:
        memory = self._read_memory()
        disk = shutil.disk_usage("/")
        docker_hostname, docker_os_name = self._docker.host_identity()
        return HostSnapshot(
            hostname=docker_hostname or platform.node(),
            # Nightwatch is containerized. Docker reports the operating system
            # of the Linux host, whereas /etc/os-release is only the image OS.
            os_name=docker_os_name or self._os_name(),
            kernel=platform.release(),
            architecture=platform.machine(),
            uptime_seconds=self._uptime_seconds(),
            cpu_count=os.cpu_count() or 1,
            cpu_percent=self._cpu_percent(),
            memory_total_bytes=memory[0],
            memory_used_bytes=memory[1],
            root_disk_total_bytes=disk.total,
            root_disk_used_bytes=disk.used,
            load_1m=self._load_1m(),
            capabilities=self._capabilities(),
        )

    @staticmethod
    def _os_name() -> str:
        try:
            release = platform.freedesktop_os_release()
            return release.get("PRETTY_NAME", platform.system())
        except OSError:
            return platform.system()

    @staticmethod
    def _uptime_seconds() -> int:
        try:
            return int(float(Path("/proc/uptime").read_text().split()[0]))
        except (OSError, ValueError, IndexError):
            return 0

    def _cpu_percent(self) -> float | None:
        try:
            values = Path("/proc/stat").read_text().splitlines()[0].split()
            times = [int(value) for value in values[1:]]
        except (OSError, ValueError, IndexError):
            return None
        total = sum(times)
        idle = times[3] + (times[4] if len(times) > 4 else 0)
        current = (total, idle)
        previous = self._previous_cpu_times
        self._previous_cpu_times = current
        if previous is None or total == previous[0]:
            return 0.0
        return round(100 * (1 - (idle - previous[1]) / (total - previous[0])), 1)

    @staticmethod
    def _read_memory() -> tuple[int, int]:
        try:
            values = {
                key.rstrip(":"): int(value) * 1024
                for key, value, *_ in (
                    line.split() for line in Path("/proc/meminfo").read_text().splitlines()
                )
            }
            total = values["MemTotal"]
            return total, total - values.get("MemAvailable", 0)
        except (OSError, ValueError, KeyError):
            return 0, 0

    @staticmethod
    def _load_1m() -> float | None:
        try:
            return round(os.getloadavg()[0], 2)
        except OSError:
            return None

    def _capabilities(self) -> list[str]:
        capabilities = ["HTTP_PROBE", "TCP_PROBE", "DNS"]
        if shutil.which("systemctl"):
            capabilities.append("SYSTEMD")
        if shutil.which("journalctl"):
            capabilities.append("JOURNAL")
        if self._docker.available():
            capabilities.append("DOCKER")
            if self._docker.events_available():
                capabilities.append("DOCKER_EVENTS")
        if TraefikAdapter().discover():
            capabilities.append("TRAEFIK")
        return capabilities
