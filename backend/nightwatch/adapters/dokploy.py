from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from nightwatch.security.redaction import redact


class DokployAdapter:
    """Read-only Dokploy project metadata; Docker remains the runtime authority."""

    def __init__(self, base_url: str | None, api_key: str | None) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._api_key = api_key
        self._cached: dict[str, str] = {}
        self._cached_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    async def github_repositories(self, github_id: str) -> list[dict[str, Any]]:
        response = await self._async_request("GET", "/api/github.getGithubRepositories", params={"githubId": github_id})
        data = self._data(response)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def github_providers(self) -> list[dict[str, Any]]:
        data = self._data(await self._async_request("GET", "/api/github.githubProviders"))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def test_github_connection(self, github_id: str) -> None:
        await self._async_request("POST", "/api/github.testConnection", json={"githubId": github_id})

    async def github_branches(self, github_id: str, owner: str, repository: str) -> list[str]:
        response = await self._async_request("GET", "/api/github.getGithubBranches", params={"githubId": github_id, "owner": owner, "repo": repository})
        data = self._data(response)
        if not isinstance(data, list):
            return []
        return [str(item.get("name")) for item in data if isinstance(item, dict) and item.get("name")]

    async def create_project(self, name: str) -> str:
        return self._id(await self._async_request("POST", "/api/project.create", json={"name": name}), "projectId")

    async def project_by_name(self, name: str) -> dict[str, Any] | None:
        """Return the authoritative Dokploy record for a project name.

        Dokploy can commit a create before returning a response shape that differs
        across releases. Callers must use this readback as their proof of state.
        """
        projects = self._projects(await self._async_request("GET", "/api/project.all"))
        wanted = name.strip().casefold()
        return next((item for item in projects if str(item.get("name") or "").strip().casefold() == wanted), None)

    async def projects(self) -> list[dict[str, Any]]:
        """Return redacted control-plane inventory, including blank resources."""
        raw = self._projects(await self._async_request("GET", "/api/project.all"))
        return [self._redact_project(item) for item in raw]

    @staticmethod
    def _redact_project(project: dict[str, Any]) -> dict[str, Any]:
        environments: list[dict[str, Any]] = []
        for environment in project.get("environments") or []:
            if not isinstance(environment, dict):
                continue
            applications = [
                {"applicationId": app.get("applicationId"), "name": app.get("name")}
                for app in environment.get("applications") or [] if isinstance(app, dict)
            ]
            environments.append({"environmentId": environment.get("environmentId"), "name": environment.get("name"), "applications": applications})
        return {"projectId": project.get("projectId"), "name": project.get("name"), "environments": environments}

    async def environment_by_name(self, project_name: str, name: str) -> dict[str, Any] | None:
        project = await self.project_by_name(project_name)
        if project is None:
            return None
        wanted = name.strip().casefold()
        environments = project.get("environments")
        if not isinstance(environments, list):
            return None
        return next((item for item in environments if isinstance(item, dict) and str(item.get("name") or "").strip().casefold() == wanted), None)

    async def application_by_name(self, project_name: str, environment_name: str, name: str) -> dict[str, Any] | None:
        environment = await self.environment_by_name(project_name, environment_name)
        if environment is None:
            return None
        applications = environment.get("applications")
        wanted = name.strip().casefold()
        if not isinstance(applications, list):
            return None
        return next((item for item in applications if isinstance(item, dict) and str(item.get("name") or "").strip().casefold() == wanted), None)

    async def create_environment(self, project_id: str, name: str) -> str:
        return self._id(await self._async_request("POST", "/api/environment.create", json={"projectId": project_id, "name": name}), "environmentId")

    async def create_application(self, environment_id: str, name: str) -> str:
        return self._id(await self._async_request("POST", "/api/application.create", json={"environmentId": environment_id, "name": name}), "applicationId")

    async def configure_application(self, application_id: str, payload: dict[str, object]) -> None:
        await self._async_request("POST", "/api/application.update", json={"applicationId": application_id, **payload})

    async def save_github_provider(self, application_id: str, payload: dict[str, object]) -> None:
        await self._async_request("POST", "/api/application.saveGithubProvider", json={"applicationId": application_id, **payload})

    async def save_build_type(self, application_id: str, payload: dict[str, object]) -> None:
        await self._async_request("POST", "/api/application.saveBuildType", json={"applicationId": application_id, **payload})

    async def application_one(self, application_id: str) -> dict[str, Any]:
        data = self._data(await self._async_request("GET", "/api/application.one", params={"applicationId": application_id}))
        if not isinstance(data, dict):
            raise DokployError("Dokploy did not return the configured application.")
        return data

    async def swarm_services(self) -> list[dict[str, Any]]:
        data = self._data(await self._async_request("GET", "/api/swarm.getNodeApps"))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def swarm_container_stats(self) -> list[dict[str, Any]]:
        data = self._data(await self._async_request("GET", "/api/swarm.getContainerStats"))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def service_logs(self, kind: str, identity: str, *, tail: int = 100, search: str | None = None) -> list[str]:
        allowed = {"application", "compose", "postgres", "mysql", "mariadb", "mongo", "redis", "libsql"}
        if kind not in allowed:
            raise DokployError("Unsupported service type for logs.")
        safe_tail = max(1, min(tail, 200))
        params: dict[str, str | int | float | bool | None] = {
            f"{kind}Id": identity,
            "tail": safe_tail,
        }
        if search:
            params["search"] = search[:120]
        data = self._data(await self._async_request("GET", f"/api/{kind}.readLogs", params=params))
        if isinstance(data, str):
            lines = data.splitlines()
        elif isinstance(data, list):
            lines = [str(item) for item in data]
        elif isinstance(data, dict):
            raw = data.get("logs") or data.get("data") or []
            lines = raw.splitlines() if isinstance(raw, str) else [str(item) for item in raw] if isinstance(raw, list) else []
        else:
            lines = []
        return [str(redact(line)) for line in lines[-safe_tail:]]

    async def save_application_environment(self, application_id: str, environment: str) -> None:
        await self._async_request("POST", "/api/application.saveEnvironment", json={"applicationId": application_id, "env": environment})

    async def create_domain(self, application_id: str, host: str, port: int) -> None:
        await self._async_request("POST", "/api/domain.create", json={"applicationId": application_id, "host": host, "port": port, "https": True, "certificateType": "letsencrypt"})

    async def deploy_application(self, application_id: str) -> None:
        # Dokploy queues deployments asynchronously and replies with an empty 2xx
        # body on some supported releases. The HTTP success status is the only
        # acknowledgement available from that endpoint.
        await self._async_request(
            "POST", "/api/application.deploy",
            json={"applicationId": application_id},
            allow_empty_response=True,
        )

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool | None] | None = None,
        json: dict[str, object] | None = None,
        allow_empty_response: bool = False,
    ) -> object:
        if not self.configured:
            raise DokployError("Dokploy URL or API key is not configured.")
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.request(method, f"{self._base_url}{path}", params=params, json=json, headers={"x-api-key": self._api_key or "", "accept": "application/json"})
        except httpx.HTTPError as exc:
            raise DokployError(f"Dokploy is unavailable while calling {path}.") from exc
        if not response.is_success:
            raise DokployError(f"Dokploy rejected {path} with HTTP {response.status_code}.")
        if allow_empty_response and not response.content.strip():
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise DokployError(f"Dokploy returned an invalid response for {path}.") from exc

    @staticmethod
    def _id(payload: object, key: str) -> str:
        data = DokployAdapter._data(payload)
        if isinstance(data, dict):
            value = data.get(key) or data.get("id")
            if isinstance(value, str) and value:
                return value
        raise DokployError(f"Dokploy did not return {key}.")

    def service_project_names(self) -> dict[str, str]:
        if not self._base_url or not self._api_key:
            return {}
        if time.monotonic() - self._cached_at < 60:
            return self._cached
        try:
            projects = self._request_projects()
        except (httpx.HTTPError, TypeError, ValueError):
            return self._cached
        mapping: dict[str, str] = {}
        detail_requests: list[tuple[str, str, str, str]] = []
        for project in projects:
            project_name = str(project.get("name") or "").strip()
            if not project_name:
                continue
            for environment in project.get("environments") or []:
                if not isinstance(environment, dict):
                    continue
                for key, service_type in (("applications", "application"), ("compose", "compose")):
                    for service in environment.get(key) or []:
                        if isinstance(service, dict) and isinstance(service.get("name"), str):
                            mapping[service["name"]] = project_name
                            service_id = service.get(f"{service_type}Id")
                            if isinstance(service_id, str):
                                detail_requests.append((service_type, service_id, project_name, service["name"]))
        # Dokploy project.all intentionally returns compact service objects. Resolve
        # the appName behind each one so Docker's Compose label joins to the human
        # project name, without exposing the API credential to the frontend.
        with ThreadPoolExecutor(max_workers=4) as executor:
            for service_type, app_name, project_name, fallback_name in executor.map(
                lambda request: self._service_app_name(*request), detail_requests
            ):
                if app_name:
                    mapping[app_name] = project_name
                mapping[fallback_name] = project_name
        self._cached, self._cached_at = mapping, time.monotonic()
        return mapping

    def _request_projects(self) -> list[dict[str, Any]]:
        for path in ("/api/project.all", "/api/trpc/project.all"):
            response = httpx.get(
                f"{self._base_url}{path}",
                headers={"x-api-key": self._api_key or "", "accept": "application/json"},
                timeout=3.0,
                follow_redirects=False,
            )
            if response.is_success:
                projects = self._projects(response.json())
                if projects:
                    return projects
        return []

    def _service_app_name(
        self, service_type: str, service_id: str, project_name: str, fallback_name: str
    ) -> tuple[str, str | None, str, str]:
        try:
            response = httpx.get(
                f"{self._base_url}/api/{service_type}.one",
                params={f"{service_type}Id": service_id},
                headers={"x-api-key": self._api_key or "", "accept": "application/json"},
                timeout=2.0,
                follow_redirects=False,
            )
            response.raise_for_status()
            data = self._data(response.json())
            app_name = data.get("appName") if isinstance(data, dict) else None
            return service_type, app_name if isinstance(app_name, str) else None, project_name, fallback_name
        except (httpx.HTTPError, TypeError, ValueError):
            return service_type, None, project_name, fallback_name

    @staticmethod
    def _projects(payload: object) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        data = DokployAdapter._data(payload)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    @staticmethod
    def _data(payload: object) -> object:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return None
        result = payload.get("result")
        data = result.get("data") if isinstance(result, dict) else payload.get("data")
        if isinstance(data, dict) and "json" in data:
            return data["json"]
        # Dokploy's REST endpoints return the resource directly, while tRPC
        # endpoints wrap it in data.json. Preserve both response shapes.
        return data if data is not None else payload


class DokployError(RuntimeError):
    pass
