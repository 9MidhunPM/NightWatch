from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from nightwatch.adapters.docker import DockerUnavailableError
from nightwatch.adapters.network import probe_tcp, resolve_dns
from nightwatch.adapters.traefik import TraefikAdapter
from nightwatch.security.redaction import redact
from nightwatch.services.docker_service import DockerService
from nightwatch.services.host_service import HostService
from nightwatch.services.topology_service import TopologyService


class EmptyInput(BaseModel):
    pass


class ContainerInput(BaseModel):
    container_id: str = Field(min_length=4, max_length=128)


class LogsInput(ContainerInput):
    tail: int = Field(default=100, ge=1, le=200)


class HttpInput(BaseModel):
    url: str = Field(min_length=8, max_length=512)


class TcpInput(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)


class DnsInput(BaseModel):
    host: str = Field(min_length=1, max_length=255)


@dataclass(frozen=True)
class ToolResult:
    resource_id: str
    summary: str
    data: dict[str, object]
    usable: bool = True


class InvestigationToolRegistry:
    """The complete Investigator surface: explicit, read-only, and bounded."""

    def __init__(
        self,
        host_service: HostService,
        docker_service: DockerService,
        topology_service: TopologyService,
        traefik_adapter: TraefikAdapter,
        *,
        timeout_seconds: float,
    ) -> None:
        self._host_service = host_service
        self._docker_service = docker_service
        self._topology_service = topology_service
        self._traefik_adapter = traefik_adapter
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def definitions() -> list[dict[str, object]]:
        def tool(
            name: str, description: str, properties: dict[str, object], required: list[str]
        ) -> dict[str, object]:
            return {
                "type": "function",
                "name": name,
                "description": description,
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            }

        return [
            tool("host_get_metrics", "Read safe managed-host metrics.", {}, []),
            tool(
                "docker_list_containers",
                "List normalized Docker containers without environment values.",
                {},
                [],
            ),
            tool(
                "docker_inspect_container",
                "Inspect normalized runtime state for one discovered container.",
                {"container_id": {"type": "string"}},
                ["container_id"],
            ),
            tool(
                "docker_get_logs",
                "Read at most 200 redacted log lines from one discovered container.",
                {
                    "container_id": {"type": "string"},
                    "tail": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                ["container_id", "tail"],
            ),
            tool("docker_list_networks", "List normalized Docker network membership.", {}, []),
            tool(
                "http_probe",
                "Probe only a hostname already present in this incident topology.",
                {"url": {"type": "string"}},
                ["url"],
            ),
            tool(
                "tcp_probe",
                "Probe a topology-related host and port without sending payload data.",
                {
                    "host": {"type": "string"},
                    "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                },
                ["host", "port"],
            ),
            tool(
                "dns_resolve",
                "Resolve a hostname already present in this incident topology.",
                {"host": {"type": "string"}},
                ["host"],
            ),
            tool(
                "traefik_get_routes",
                "Read safe Traefik routing state derived from local labels.",
                {},
                [],
            ),
            tool(
                "topology_get_related_resources",
                "Read the compact topology slice related to this incident.",
                {},
                [],
            ),
        ]

    async def execute(
        self,
        name: str,
        raw_arguments: str,
        affected_resource_ids: list[str],
        trigger: dict[str, object],
    ) -> ToolResult:
        try:
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise TypeError("Tool arguments must be an object.")
        except (json.JSONDecodeError, TypeError) as exc:
            return ToolResult(
                "investigator", "Tool input was rejected.", {"error": str(exc)}, False
            )
        try:
            result = await self._execute(name, arguments, affected_resource_ids, trigger)
        except (ValidationError, ValueError) as exc:
            return ToolResult(
                "investigator", "Tool input was rejected.", {"error": str(exc)}, False
            )
        except DockerUnavailableError:
            return ToolResult(
                "investigator",
                "Tool could not collect evidence safely.",
                {"error": "TOOL_UNAVAILABLE"},
                False,
            )
        return ToolResult(result.resource_id, result.summary, redact(result.data))

    async def _execute(
        self, name: str, args: dict[str, Any], affected: list[str], trigger: dict[str, object]
    ) -> ToolResult:
        if name == "host_get_metrics":
            host = await self._host_service.get_host()
            return ToolResult(
                "host:local-host",
                f"Managed host {host.hostname} metrics collected.",
                host.model_dump(mode="json"),
            )
        if name in {
            "docker_list_containers",
            "docker_list_networks",
            "docker_inspect_container",
            "docker_get_logs",
        }:
            inventory = await self._docker_service.inventory(publish_event=False)
            container_ids = {container.id for container in inventory.containers}
            if name == "docker_list_containers":
                return ToolResult(
                    "docker",
                    f"Collected {len(inventory.containers)} normalized containers.",
                    {"containers": [item.model_dump(mode="json") for item in inventory.containers]},
                )
            if name == "docker_list_networks":
                return ToolResult(
                    "docker",
                    f"Collected {len(inventory.networks)} Docker networks.",
                    {"networks": [item.model_dump(mode="json") for item in inventory.networks]},
                )
            if name == "docker_get_logs":
                parsed_logs = LogsInput.model_validate(args)
                if parsed_logs.container_id not in container_ids:
                    raise ValueError("Container is not in the current inventory.")
                logs = await self._docker_service.logs(parsed_logs.container_id, parsed_logs.tail)
                return ToolResult(
                    f"container:{parsed_logs.container_id}",
                    f"Collected {len(logs)} bounded log lines.",
                    {"lines": logs},
                )
            parsed_container = ContainerInput.model_validate(args)
            if parsed_container.container_id not in container_ids:
                raise ValueError("Container is not in the current inventory.")
            container = next(
                item for item in inventory.containers if item.id == parsed_container.container_id
            )
            return ToolResult(
                f"container:{container.id}",
                f"Container {container.name} inspected.",
                container.model_dump(mode="json"),
            )
        if name == "traefik_get_routes":
            routes = await self._topology_service.traefik_routes()
            return ToolResult(
                "traefik",
                f"Collected {len(routes)} discovered Traefik routes.",
                {"routes": [route.model_dump() for route in routes]},
            )
        if name == "topology_get_related_resources":
            snapshot = await self._topology_service.related_slice(affected)
            return ToolResult(
                "topology",
                "Collected the incident topology slice.",
                snapshot.model_dump(mode="json"),
            )
        allowed_hosts, allowed_ports = await self._network_scope(trigger, affected)
        if name == "http_probe":
            parsed_http = HttpInput.model_validate(args)
            parsed_url = urlparse(parsed_http.url)
            url_host = parsed_url.hostname
            if (
                not url_host
                or parsed_url.username
                or parsed_url.password
                or parsed_url.query
                or parsed_url.fragment
            ):
                raise ValueError("Probe URL must not contain credentials or a query.")
            if url_host not in allowed_hosts or (
                parsed_url.port and parsed_url.port not in allowed_ports
            ):
                raise ValueError("URL host is outside the incident topology scope.")
            from nightwatch.adapters.http import probe_http

            result = await probe_http(parsed_http.url, self._timeout_seconds)
            return ToolResult(
                f"url:{parsed_http.url}",
                f"HTTP probe returned {result.status_code or result.error_type or 'success'}.",
                result.model_dump(mode="json"),
            )
        if name in {"tcp_probe", "dns_resolve"}:
            if name == "tcp_probe":
                parsed_tcp = TcpInput.model_validate(args)
                if parsed_tcp.host not in allowed_hosts or parsed_tcp.port not in allowed_ports:
                    raise ValueError("Host is outside the incident topology scope.")
                tcp_result = await probe_tcp(
                    parsed_tcp.host, parsed_tcp.port, self._timeout_seconds
                )
                return ToolResult(
                    f"tcp:{parsed_tcp.host}:{parsed_tcp.port}",
                    f"TCP probe to {parsed_tcp.host}:{parsed_tcp.port} {'succeeded' if tcp_result.reachable else 'failed'}.",
                    tcp_result.model_dump(mode="json"),
                )
            parsed_dns = DnsInput.model_validate(args)
            if parsed_dns.host not in allowed_hosts:
                raise ValueError("Host is outside the incident topology scope.")
            addresses = await resolve_dns(parsed_dns.host)
            return ToolResult(
                f"dns:{parsed_dns.host}",
                f"DNS resolved {parsed_dns.host} to {len(addresses)} address(es).",
                {"addresses": addresses},
            )
        raise ValueError("Tool is not registered for the Investigator.")

    async def _network_scope(
        self, trigger: dict[str, object], affected: list[str]
    ) -> tuple[set[str], set[int]]:
        hosts: set[str] = set()
        ports: set[int] = set()
        url = trigger.get("url")
        if isinstance(url, str):
            parsed = urlparse(url)
            if parsed.hostname:
                hosts.add(parsed.hostname)
            if parsed.port:
                ports.add(parsed.port)
        snapshot = await self._topology_service.related_slice(affected)
        hosts.update(
            node.label for node in snapshot.nodes if node.type in {"DOMAIN", "SERVICE", "CONTAINER"}
        )
        for node in snapshot.nodes:
            for value in (node.attributes.get("target_port", ""), node.attributes.get("ports", "")):
                for item in value.replace(",", " ").split():
                    candidate = item.split("/", maxsplit=1)[0]
                    if candidate.isdigit():
                        ports.add(int(candidate))
        return hosts, ports
