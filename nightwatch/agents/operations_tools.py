from __future__ import annotations

from nightwatch.models.deployment_api import DeploymentPlanRequest, InferredDeploymentRequest
from nightwatch.services.deployment_service import DeploymentService
from nightwatch.services.incident_service import IncidentService
from nightwatch.services.topology_service import TopologyService


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
    ) -> None:
        self._topology = topology
        self._incidents = incidents
        self._deployment = deployment

    @staticmethod
    def definitions() -> list[dict[str, object]]:
        empty = {"type": "object", "properties": {}, "additionalProperties": False}
        project = {
            "type": "object",
            "properties": {"project": {"type": "string", "minLength": 1, "maxLength": 120}},
            "required": ["project"],
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
