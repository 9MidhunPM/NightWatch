from __future__ import annotations

import re
from typing import Any

import docker
from docker.errors import DockerException

from nightwatch.models.traefik_api import TraefikRoute


class TraefikAdapter:
    """Read routes from local Docker labels when the Traefik API is not configured."""

    _ROUTER_RULE = re.compile(r"^traefik\.http\.routers\.([^.]+)\.rule$")
    _HOST = re.compile(r"Host\(`([^`]+)`\)|Host\('([^']+)'\)|Host\(\"([^\"]+)\"\)")

    def __init__(self, timeout_seconds: int = 3) -> None:
        self._timeout_seconds = timeout_seconds

    def discover(self) -> list[TraefikRoute]:
        try:
            client = docker.from_env(timeout=self._timeout_seconds)
            client.ping()
            routes = [
                route
                for container in client.containers.list(all=True)
                for route in self._routes_for_container(container.attrs)
            ]
        except DockerException:
            return []
        return sorted(routes, key=lambda route: (route.router_name, route.container_name))

    @classmethod
    def _routes_for_container(cls, attrs: dict[str, Any]) -> list[TraefikRoute]:
        labels = (attrs.get("Config", {}) or {}).get("Labels") or {}
        routes: list[TraefikRoute] = []
        for key, rule in labels.items():
            match = cls._ROUTER_RULE.match(key)
            if not match or not isinstance(rule, str):
                continue
            router_name = match.group(1)
            service_name = labels.get(f"traefik.http.routers.{router_name}.service")
            if not isinstance(service_name, str):
                service_name = router_name
            port = labels.get(f"traefik.http.services.{service_name}.loadbalancer.server.port")
            middleware = labels.get(f"traefik.http.routers.{router_name}.middlewares")
            routes.append(
                TraefikRoute(
                    id=f"{attrs.get('Id', '')}:{router_name}",
                    router_name=router_name,
                    rule=rule,
                    domains=cls._domains(rule),
                    service_name=service_name,
                    target_port=int(port) if isinstance(port, str) and port.isdigit() else None,
                    container_id=str(attrs.get("Id", "")),
                    container_name=str(attrs.get("Name", "")).lstrip("/"),
                    middleware_names=sorted(item.strip() for item in middleware.split(","))
                    if isinstance(middleware, str)
                    else [],
                )
            )
        return routes

    @classmethod
    def _domains(cls, rule: str) -> list[str]:
        return sorted(
            {next(item for item in match.groups() if item) for match in cls._HOST.finditer(rule)}
        )
