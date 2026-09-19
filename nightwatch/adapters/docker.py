from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import docker
from docker.errors import DockerException

from nightwatch.models.docker_api import (
    DockerContainer,
    DockerInventory,
    DockerNetwork,
    DockerNetworkMember,
    DockerPort,
)
from nightwatch.models.operations_api import ContainerUsage


class DockerUnavailableError(RuntimeError):
    pass


class DockerAdapter:
    """Read-only, normalized access to the local Docker daemon."""

    _SAFE_LABEL_PREFIXES = ("com.docker.compose.", "org.opencontainers.image.")
    _SAFE_LABELS = frozenset({"nightwatch.demo"})

    def __init__(self, timeout_seconds: int = 3) -> None:
        self._timeout_seconds = timeout_seconds

    def available(self) -> bool:
        try:
            client = self._client()
            client.ping()
        except DockerException:
            return False
        return True

    def events_available(self) -> bool:
        try:
            client = self._client()
            stream = client.events(decode=True, since=int(time.time()), until=int(time.time()))
            next(stream, None)
            stream.close()
        except DockerException:
            return False
        return True

    def host_identity(self) -> tuple[str | None, str | None]:
        """Return Docker's view of the managed host, never container /etc metadata."""
        try:
            client = self._client()
            client.ping()
            info = client.info()
        except DockerException:
            return None, None
        name = str(info.get("Name") or "").strip() or None
        operating_system = str(info.get("OperatingSystem") or "").strip() or None
        return name, operating_system

    def discover(self) -> DockerInventory:
        discovered_at = datetime.now(UTC)
        try:
            client = self._client()
            client.ping()
            containers = [self._container(item.attrs) for item in client.containers.list(all=True)]
            networks = [self._network(item.attrs) for item in client.networks.list()]
        except DockerException as exc:
            raise DockerUnavailableError(
                "Docker is unavailable to the Nightwatch backend."
            ) from exc
        return DockerInventory(
            available=True,
            discovered_at=discovered_at,
            containers=sorted(containers, key=lambda container: container.name),
            networks=sorted(networks, key=lambda network: network.name),
        )

    def logs(self, container_id: str, tail: int) -> list[str]:
        """Read a deliberately bounded log tail; never returns inspect/environment data."""
        safe_tail = max(1, min(tail, 200))
        try:
            client = self._client()
            client.ping()
            raw = client.containers.get(container_id).logs(tail=safe_tail, timestamps=True)
        except DockerException as exc:
            raise DockerUnavailableError(
                "Docker logs are unavailable to the Nightwatch backend."
            ) from exc
        return raw.decode("utf-8", errors="replace").splitlines()[-safe_tail:]

    def usage(self) -> list[ContainerUsage]:
        observed_at = datetime.now(UTC)
        try:
            client = self._client()
            client.ping()
            containers = client.containers.list(all=False)
            # Docker's non-streaming stats endpoint is independent per container.  Sampling
            # them serially turns one slow container into a minute-long page and chat request.
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(containers)))) as executor:
                samples = list(
                    executor.map(lambda container: self._usage_for(container, observed_at), containers)
                )
                return [sample for sample in samples if sample is not None]
        except DockerException as exc:
            raise DockerUnavailableError("Docker statistics are unavailable to the Nightwatch backend.") from exc

    @staticmethod
    def _usage_for(container: Any, observed_at: datetime) -> ContainerUsage | None:
        try:
            stats = container.stats(stream=False)
        except DockerException:
            # A single stopped or overloaded workload must not make the whole
            # inventory disappear. Its current state still comes from discovery.
            return None
        cpu, previous = stats.get("cpu_stats") or {}, stats.get("precpu_stats") or {}
        cpu_total = int((cpu.get("cpu_usage") or {}).get("total_usage") or 0)
        previous_total = int((previous.get("cpu_usage") or {}).get("total_usage") or 0)
        system_total, previous_system = int(cpu.get("system_cpu_usage") or 0), int(previous.get("system_cpu_usage") or 0)
        count = len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or 1
        cpu_percent = round(((cpu_total - previous_total) / (system_total - previous_system)) * count * 100, 2) if system_total > previous_system else None
        memory = stats.get("memory_stats") or {}; used, limit = memory.get("usage"), memory.get("limit")
        network_values = list((stats.get("networks") or {}).values())
        return ContainerUsage(container_id=container.id, cpu_percent=cpu_percent, memory_used_bytes=int(used) if used is not None else None, memory_limit_bytes=int(limit) if limit is not None else None, memory_percent=round(int(used) / int(limit) * 100, 2) if used and limit else None, network_rx_bytes=sum(int(item.get("rx_bytes") or 0) for item in network_values), network_tx_bytes=sum(int(item.get("tx_bytes") or 0) for item in network_values), observed_at=observed_at)

    def _client(self) -> docker.DockerClient:
        return docker.from_env(timeout=self._timeout_seconds)

    @classmethod
    def _container(cls, attrs: dict[str, Any]) -> DockerContainer:
        state = attrs.get("State", {})
        config = attrs.get("Config", {})
        host_config = attrs.get("HostConfig", {})
        settings = attrs.get("NetworkSettings", {})
        labels = cls._safe_labels(config.get("Labels") or {})
        ports = cls._ports(settings.get("Ports") or {})
        networks = sorted((settings.get("Networks") or {}).keys())
        health = (state.get("Health") or {}).get("Status")
        compose_project = labels.get("com.docker.compose.project")
        return DockerContainer(
            id=str(attrs.get("Id", "")),
            name=str(attrs.get("Name", "")).lstrip("/"),
            image=str(config.get("Image") or attrs.get("Image") or "unknown"),
            state=str(state.get("Status", "unknown")),
            health=str(health) if health else None,
            created_at=cls._datetime(attrs.get("Created")),
            started_at=cls._datetime(state.get("StartedAt")),
            restart_count=int(state.get("RestartCount") or 0),
            ports=ports,
            networks=networks,
            restart_policy=(host_config.get("RestartPolicy") or {}).get("Name") or None,
            labels=labels,
            compose_project=compose_project,
            compose_service=labels.get("com.docker.compose.service"),
            resource_type=cls._resource_type(str(config.get("Image") or attrs.get("Image") or "")),
        )

    @staticmethod
    def _network(attrs: dict[str, Any]) -> DockerNetwork:
        containers = attrs.get("Containers") or {}
        return DockerNetwork(
            id=str(attrs.get("Id", "")),
            name=str(attrs.get("Name", "")),
            driver=str(attrs.get("Driver", "unknown")),
            internal=bool(attrs.get("Internal", False)),
            containers=sorted(
                [
                    DockerNetworkMember(id=str(container_id), name=str(item.get("Name", "")))
                    for container_id, item in containers.items()
                ],
                key=lambda container: container.name,
            ),
        )

    @staticmethod
    def _ports(raw_ports: dict[str, Any]) -> list[DockerPort]:
        ports: list[DockerPort] = []
        for internal, bindings in raw_ports.items():
            if not bindings:
                ports.append(DockerPort(internal=str(internal)))
                continue
            for binding in bindings:
                ports.append(
                    DockerPort(
                        internal=str(internal),
                        host_ip=binding.get("HostIp"),
                        host_port=int(binding["HostPort"]) if binding.get("HostPort") else None,
                    )
                )
        return sorted(ports, key=lambda port: (port.internal, port.host_port or 0))

    @classmethod
    def _safe_labels(cls, labels: dict[str, str]) -> dict[str, str]:
        return {
            key: value
            for key, value in labels.items()
            if key.startswith(cls._SAFE_LABEL_PREFIXES) or key in cls._SAFE_LABELS
        }

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value or value.startswith("0001-01-01"):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _resource_type(image: str) -> str:
        image_name = image.lower().split("@", maxsplit=1)[0].split(":", maxsplit=1)[0]
        if image_name in {"postgres", "postgresql"} or "/postgres" in image_name:
            return "DATABASE"
        if image_name == "redis" or "/redis" in image_name:
            return "CACHE"
        if image_name == "traefik" or "/traefik" in image_name:
            return "REVERSE_PROXY"
        return "CONTAINER"
