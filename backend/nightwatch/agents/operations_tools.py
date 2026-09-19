from __future__ import annotations

from nightwatch.adapters.dokploy import DokployAdapter, DokployError
from nightwatch.models.deployment_api import DeploymentPlanRequest, InferredDeploymentRequest
from nightwatch.services.beszel_service import BeszelService
from nightwatch.services.deployment_service import DeploymentService
from nightwatch.services.incident_service import IncidentService
from nightwatch.services.topology_service import TopologyService
from nightwatch.services.world_service import WorldService


class OperationsToolBroker:
    """Safe, model-callable read tools for the operations agent.

    This is deliberately narrower than the backend's adapter surface. It returns
    normalized, redacted topology and deployment facts only; Codex never receives
    a shell, Docker client, API credential, or mutable infrastructure handle.
    """

    def __init__(
        self,
        topology: TopologyService,
        incidents: IncidentService,
        deployment: DeploymentService,
        world: WorldService | None = None,
        dokploy: DokployAdapter | None = None,
        beszel: BeszelService | None = None,
    ) -> None:
        self._topology = topology
        self._incidents = incidents
        self._deployment = deployment
        self._world = world
        self._dokploy = dokploy
        self._beszel = beszel

    @staticmethod
    def definitions() -> list[dict[str, object]]:
        empty = {"type": "object", "properties": {}, "additionalProperties": False}
        project = {
            "type": "object",
            "properties": {"project": {"type": "string", "minLength": 1, "maxLength": 120}},
            "required": ["project"],
            "additionalProperties": False,
        }
        lookup = {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 180}},
            "required": ["query"],
            "additionalProperties": False,
        }
        resource_id = {
            "type": "object",
            "properties": {"resource_id": {"type": "string", "minLength": 1, "maxLength": 300}},
            "required": ["resource_id"],
            "additionalProperties": False,
        }
        metrics = {
            "type": "object",
            "properties": {
                "resource_id": {"type": ["string", "null"], "maxLength": 300},
                "range": {"type": "string", "enum": ["1h", "24h", "7d", "30d"]},
            },
            "required": ["range"],
            "additionalProperties": False,
        }
        logs = {
            "type": "object",
            "properties": {
                "resource_id": {"type": "string", "minLength": 1, "maxLength": 300},
                "tail": {"type": "integer", "minimum": 1, "maximum": 200},
                "search": {"type": ["string", "null"], "maxLength": 120},
            },
            "required": ["resource_id"],
            "additionalProperties": False,
        }
        project_plan = {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "minLength": 2, "maxLength": 80},
                "service_name": {"type": "string", "minLength": 2, "maxLength": 80},
            },
            "required": ["project_name"], "additionalProperties": False,
        }
        deployment = {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "minLength": 1, "maxLength": 120},
                "repository": {"type": "string", "minLength": 1, "maxLength": 160},
                "branch": {"type": "string", "minLength": 1, "maxLength": 200},
                "project_name": {"type": "string", "minLength": 2, "maxLength": 80},
                "service_name": {"type": "string", "minLength": 2, "maxLength": 80},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "build_type": {"type": "string", "enum": ["dockerfile", "static"]},
                "build_path": {"type": "string", "minLength": 1, "maxLength": 300},
                "dockerfile": {"type": ["string", "null"], "maxLength": 300},
                "domain": {"type": ["string", "null"], "maxLength": 253},
                "manifest_notes": {"type": "string", "minLength": 5, "maxLength": 3000},
            },
            "required": ["owner", "repository", "branch", "project_name", "service_name", "port", "manifest_notes"],
            "additionalProperties": False,
        }
        inferred_deployment = {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "minLength": 1, "maxLength": 120},
                "repository": {"type": "string", "minLength": 1, "maxLength": 160},
                "project_name": {"type": "string", "minLength": 2, "maxLength": 80},
                "service_name": {"type": "string", "minLength": 2, "maxLength": 80},
                "domain": {"type": "string", "minLength": 3, "maxLength": 253},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
            },
            "required": ["owner", "repository", "project_name", "service_name", "domain"],
            "additionalProperties": False,
        }
        return [
            {"type": "function", "name": "nw_list_projects", "description": "List observed Dokploy/Compose projects and their containers. Use this before answering a project mapping question.", "inputSchema": empty},
            {"type": "function", "name": "nw_find_project_containers", "description": "Find containers belonging to an observed project. Use exact or partial project names; report no match rather than guessing.", "inputSchema": project},
            {"type": "function", "name": "nw_get_topology", "description": "Read a bounded infrastructure topology summary including routes and dependencies.", "inputSchema": empty},
            {"type": "function", "name": "nw_find_resource", "description": "Find Dokploy resources by human name, app name, domain, or stable resource id. Use this before inspecting a service.", "inputSchema": lookup},
            {"type": "function", "name": "nw_get_resource_detail", "description": "Read one resource's redacted deployment configuration, replicas, runtime health, live metrics, domains, networks, connections, and recent deployments.", "inputSchema": resource_id},
            {"type": "function", "name": "nw_get_project_detail", "description": "Read every resource and connection in a named project from the unified evidence graph.", "inputSchema": project},
            {"type": "function", "name": "nw_get_metrics", "description": "Read current resource or host metrics and Beszel history for a supported time range.", "inputSchema": metrics},
            {"type": "function", "name": "nw_get_resource_logs", "description": "Read at most 200 redacted recent log lines for a resource. Use only when logs are relevant to the question.", "inputSchema": logs},
            {"type": "function", "name": "nw_get_incidents", "description": "Read current incidents and affected resources.", "inputSchema": empty},
            {"type": "function", "name": "nw_get_deployment_readiness", "description": "Validate Dokploy and GitHub repository discovery readiness without changing anything.", "inputSchema": empty},
            {"type": "function", "name": "nw_list_repositories", "description": "List repositories connected through the configured Dokploy GitHub provider. Use before preparing a deployment.", "inputSchema": empty},
            {"type": "function", "name": "nw_get_action_context", "description": "Read authoritative Dokploy control-plane projects, blank services, and persisted action outcomes. Use this before saying a prior project or service is missing.", "inputSchema": empty},
            {"type": "function", "name": "nw_prepare_project", "description": "Create a persisted approval-gated plan for a Dokploy project and, when requested, a blank application service. Inspect available project facts first; repository details are not needed for a blank service. It never changes Dokploy until the operator approves the exact plan in Nightwatch.", "inputSchema": project_plan},
            {"type": "function", "name": "nw_prepare_deployment", "description": "Create a persisted, approval-gated Dokploy deployment plan. This writes only the plan; it never creates or deploys a Dokploy project until the operator explicitly approves it in Nightwatch.", "inputSchema": deployment},
            {"type": "function", "name": "nw_prepare_inferred_deployment", "description": "Inspect an existing Dokploy service and connected repository, infer safe build settings, then prepare one exact approval-gated deployment plan. If the user explicitly gives an application port, pass port and it overrides repository inference.", "inputSchema": inferred_deployment},
        ]

    async def execute(self, name: str, arguments: object) -> dict[str, object]:
        if not isinstance(arguments, dict):
            return {"ok": False, "error": "Tool arguments must be an object."}
        arguments = dict(arguments)
        conversation_id = arguments.pop("__conversation_id", None)
        if name == "nw_list_projects":
            return await self._projects()
        if name == "nw_find_project_containers":
            project = arguments.get("project")
            if not isinstance(project, str) or not project.strip():
                return {"ok": False, "error": "A project name is required."}
            return await self._project_containers(project)
        if name == "nw_get_topology":
            snapshot = await self._topology.snapshot(publish_event=False)
            return {"ok": snapshot.available, "generated_at": snapshot.generated_at.isoformat(), "resources": len(snapshot.nodes), "connections": len(snapshot.edges), "sources": snapshot.sources, "routes": [{"label": node.label, "detail": node.detail, "health": node.health} for node in snapshot.nodes if node.type in {"ROUTE", "DOMAIN"}][:50]}
        if name == "nw_find_resource":
            return self._find_resource(str(arguments.get("query") or ""))
        if name == "nw_get_resource_detail":
            return self._resource_detail(str(arguments.get("resource_id") or ""))
        if name == "nw_get_project_detail":
            return self._project_detail(str(arguments.get("project") or ""))
        if name == "nw_get_metrics":
            return await self._metrics(arguments)
        if name == "nw_get_resource_logs":
            return await self._logs(arguments)
        if name == "nw_get_incidents":
            incidents = await self._incidents.list_incidents()
            return {"ok": True, "incidents": [{"id": item.id, "title": item.title, "state": item.state, "severity": item.severity, "affected_resource_ids": item.affected_resource_ids} for item in incidents[:30]]}
        if name == "nw_get_deployment_readiness":
            status = await self._deployment.validated_status()
            return {"ok": status.configured, "message": status.message, "provider_name": status.provider_name, "repository_count": status.repository_count, "diagnostic_code": status.diagnostic_code}
        if name == "nw_list_repositories":
            repositories = await self._deployment.repositories()
            return {"ok": True, "repositories": [item.model_dump() for item in repositories[:100]]}
        if name == "nw_get_action_context":
            return {"ok": True, **await self._deployment.action_context(conversation_id if isinstance(conversation_id, str) else None)}
        if name == "nw_prepare_project":
            project_name = arguments.get("project_name")
            if not isinstance(project_name, str):
                return {"ok": False, "error": "A project name is required."}
            try:
                service_name = arguments.get("service_name")
                plan = await self._deployment.create_project_plan(project_name, service_name if isinstance(service_name, str) else None, conversation_id if isinstance(conversation_id, str) else None)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "plan": plan, "message": "Plan is awaiting explicit approval; no Dokploy project has been created yet."}
        if name == "nw_prepare_deployment":
            try:
                if isinstance(conversation_id, str):
                    arguments["conversation_id"] = conversation_id
                deployment_plan = await self._deployment.create_plan(DeploymentPlanRequest.model_validate(arguments))
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "plan": deployment_plan.model_dump(mode="json"), "message": "Plan is awaiting explicit approval; no Dokploy project or service has been created yet."}
        if name == "nw_prepare_inferred_deployment":
            try:
                if isinstance(conversation_id, str):
                    arguments["conversation_id"] = conversation_id
                inferred_plan = await self._deployment.infer_plan(InferredDeploymentRequest.model_validate(arguments))
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "plan": inferred_plan.model_dump(mode="json"), "message": "Inferred deployment plan is awaiting explicit approval; no deployment has started."}
        return {"ok": False, "error": "Unknown Nightwatch tool."}

    def _find_resource(self, query: str) -> dict[str, object]:
        if self._world is None:
            return {"ok": False, "error": "World evidence is unavailable."}
        needle = query.strip().casefold()
        matches = []
        for project in self._world.current.projects:
            for resource in project.resources:
                haystack = [resource.id, resource.name, resource.app_name, project.name]
                haystack.extend(domain.url for domain in resource.domains)
                if any(needle in value.casefold() for value in haystack):
                    matches.append({
                        "resource_id": resource.id,
                        "name": resource.name,
                        "app_name": resource.app_name,
                        "kind": resource.kind,
                        "project": project.name,
                        "health": resource.health,
                        "runtime": resource.runtime_state,
                    })
        return {
            "ok": bool(matches),
            "matches": matches[:30],
            "evidence": self._evidence("world:resources", "world", f"Matched {len(matches)} resources."),
            "message": None if matches else "No resource matched that identifier.",
        }

    def _resource_detail(self, resource_id: str) -> dict[str, object]:
        if self._world is None:
            return {"ok": False, "error": "World evidence is unavailable."}
        for project in self._world.current.projects:
            resource = next((item for item in project.resources if item.id == resource_id), None)
            if resource is None:
                continue
            connections = [
                item.model_dump(mode="json")
                for item in self._world.current.connections
                if item.source == resource.id or item.target == resource.id
            ]
            detail = resource.model_dump(mode="json")
            detail["project"] = project.name
            detail["connections"] = connections
            return {
                "ok": True,
                "resource": detail,
                "evidence": self._evidence(resource.id, "world", f"Observed {resource.name} as {resource.health} with {resource.runtime_state}."),
            }
        return {"ok": False, "error": "Resource was not found."}

    def _project_detail(self, requested: str) -> dict[str, object]:
        if self._world is None:
            return {"ok": False, "error": "World evidence is unavailable."}
        needle = requested.strip().casefold().replace(" ", "").replace("-", "")
        project = next(
            (
                item for item in self._world.current.projects
                if needle in item.name.casefold().replace(" ", "").replace("-", "")
                or item.name.casefold().replace(" ", "").replace("-", "") in needle
            ),
            None,
        )
        if project is None:
            return {"ok": False, "message": "No project matched that name."}
        resource_ids = {item.id for item in project.resources}
        return {
            "ok": True,
            "project": project.model_dump(mode="json"),
            "connections": [item.model_dump(mode="json") for item in self._world.current.connections if item.source in resource_ids or item.target in resource_ids],
            "evidence": self._evidence(f"project:{project.id}", "world", f"Observed {len(project.resources)} resources in {project.name}."),
        }

    async def _metrics(self, arguments: dict[str, object]) -> dict[str, object]:
        range_name = str(arguments.get("range") or "24h")
        resource_id = arguments.get("resource_id")
        if self._world is None or self._beszel is None:
            return {"ok": False, "error": "Telemetry evidence is unavailable."}
        if not isinstance(resource_id, str) or not resource_id:
            series = await self._beszel.history(range_name)
            return {
                "ok": series.available,
                "current": self._world.current.host_metrics.model_dump(mode="json") if self._world.current.host_metrics else None,
                "history": series.model_dump(mode="json"),
                "evidence": self._evidence("host:metrics", series.source, f"Read {len(series.points)} host samples."),
            }
        detail = self._resource_detail(resource_id)
        resource = detail.get("resource")
        if not isinstance(resource, dict):
            return detail
        app_name = str(resource.get("app_name") or "")
        compose_service = resource.get("compose_service")
        container_name = (
            f"{app_name}-{compose_service}"
            if isinstance(compose_service, str) and compose_service
            else app_name
        )
        series = await self._beszel.history(range_name, container_name=container_name)
        return {
            "ok": True,
            "current": resource.get("metrics"),
            "history": series.model_dump(mode="json"),
            "evidence": self._evidence(resource_id, "beszel", f"Read current metrics and {len(series.points)} historical samples."),
        }

    async def _logs(self, arguments: dict[str, object]) -> dict[str, object]:
        if self._dokploy is None:
            return {"ok": False, "error": "Dokploy log access is unavailable."}
        resource_id = str(arguments.get("resource_id") or "")
        parts = resource_id.split(":")
        if len(parts) < 3 or parts[0] != "dokploy":
            return {"ok": False, "error": "Logs require a Dokploy resource id."}
        kind, identity = parts[1], parts[2]
        raw_tail = arguments.get("tail")
        tail = raw_tail if isinstance(raw_tail, int) else 100
        try:
            lines = await self._dokploy.service_logs(
                kind,
                identity,
                tail=tail,
                search=str(arguments["search"]) if arguments.get("search") else None,
            )
        except DokployError as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "lines": lines,
            "evidence": self._evidence(resource_id, "dokploy_logs", f"Read {len(lines)} redacted log lines."),
        }

    def _evidence(self, resource_id: str, source: str, summary: str) -> list[dict[str, str]]:
        observed = self._world.current.generated_at.isoformat() if self._world else ""
        return [{"resource_id": resource_id, "source": source, "observed_at": observed, "summary": summary}]

    async def _projects(self) -> dict[str, object]:
        snapshot = await self._topology.snapshot(publish_event=False)
        projects: dict[str, list[dict[str, str]]] = {}
        for node in snapshot.nodes:
            if node.type not in {"SERVICE", "CONTAINER", "DATABASE", "CACHE", "REVERSE_PROXY"}:
                continue
            project = node.attributes.get("project_name") or node.attributes.get("compose_project")
            if project:
                projects.setdefault(project, []).append({"name": node.label, "id": node.id, "state": node.attributes.get("state", "unknown"), "health": node.health, "service": node.attributes.get("compose_service", "")})
        return {"ok": True, "projects": [{"project": project, "containers": containers} for project, containers in sorted(projects.items())]}

    async def _project_containers(self, requested: str) -> dict[str, object]:
        projects = await self._projects()
        needle = requested.casefold().replace(" ", "").replace("-", "")
        matches: list[dict[str, object]] = []
        entries = projects.get("projects")
        if not isinstance(entries, list):
            return {"ok": False, "requested_project": requested, "matches": matches, "message": "Project inventory is unavailable."}
        for item in entries:
            if not isinstance(item, dict):
                continue
            project = item.get("project")
            if not isinstance(project, str):
                continue
            normalized = str(project).casefold().replace(" ", "").replace("-", "")
            if needle in normalized or normalized in needle:
                matches.append(item)
        return {"ok": bool(matches), "requested_project": requested, "matches": matches, "message": "No observed project matched that name." if not matches else None}
