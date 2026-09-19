from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from openai import AsyncOpenAI

from nightwatch.agents.app_server import CodexAppServer
from nightwatch.agents.operations_tools import OperationsToolBroker
from nightwatch.models.operations_api import (
    AgentCitation,
    AgentFinding,
    AgentMessageResponse,
    AgentStatusResponse,
    OperationsReport,
    ResourceSnapshot,
)
from nightwatch.services.deployment_service import DeploymentService
from nightwatch.services.docker_service import DockerService
from nightwatch.services.host_service import HostService
from nightwatch.services.incident_service import IncidentService
from nightwatch.services.topology_service import TopologyService


class OperationsService:
    """Read-only operational summary used by the console, reports, and chat."""

    def __init__(self, docker: DockerService, host: HostService, incidents: IncidentService, topology: TopologyService | None = None, deployment: DeploymentService | None = None, tool_broker: OperationsToolBroker | None = None, *, api_key: str | None = None, model: str = "gpt-5.6-luna", app_server: CodexAppServer | None = None) -> None:
        self._docker, self._host, self._incidents = docker, host, incidents
        self._topology = topology
        self._deployment = deployment
        self._tool_broker = tool_broker
        self._client = AsyncOpenAI(api_key=api_key, timeout=20) if api_key else None
        self._model = model
        self._last_provider_success_at: datetime | None = None
        self._resource_cache: ResourceSnapshot | None = None
        self._resource_cache_at = 0.0
        self._resource_lock = asyncio.Lock()
        self._app_server = app_server

    def agent_status(self) -> AgentStatusResponse:
        if self._app_server and self._app_server.available:
            return AgentStatusResponse(available=True, model=self._model, message=self._app_server.message, last_provider_success_at=self._last_provider_success_at, engine="codex_app_server", tool_count=self._app_server.tool_count)
        if self._client is None:
            return AgentStatusResponse(available=False, message="Codex app-server is unavailable. Check OPENAI_API_KEY and NW_CODEX_APP_SERVER_ENABLED, then redeploy the backend.", engine="unavailable")
        return AgentStatusResponse(available=False, model=self._model, message="An OpenAI key is present but Codex app-server is not active; Nightwatch will return deterministic local evidence only.", last_provider_success_at=self._last_provider_success_at, engine="local_evidence")

    def set_topology(self, topology: TopologyService) -> None:
        self._topology = topology

    def set_deployment(self, deployment: DeploymentService) -> None:
        self._deployment = deployment

    def set_tool_broker(self, tool_broker: OperationsToolBroker) -> None:
        self._tool_broker = tool_broker

    async def resources(self) -> ResourceSnapshot:
        if self._resource_cache is not None and time.monotonic() - self._resource_cache_at < 5:
            return self._resource_cache
        async with self._resource_lock:
            if self._resource_cache is not None and time.monotonic() - self._resource_cache_at < 5:
                return self._resource_cache
            inventory = await self._docker.inventory(publish_event=False)
            snapshot = ResourceSnapshot(
                containers=inventory.containers,
                usage=await self._docker.usage(),
                observed_at=datetime.now(UTC),
            )
            self._resource_cache, self._resource_cache_at = snapshot, time.monotonic()
            return snapshot

    async def report(self, resources: ResourceSnapshot | None = None) -> OperationsReport:
        current_resources = resources if resources is not None else await self.resources()
        host, incidents = await asyncio.gather(
            self._host.get_host(publish_event=False),
            self._incidents.list_incidents(),
        )
        active = sum(item.state != "RESOLVED" for item in incidents)
        unhealthy = sum(item.health == "unhealthy" or item.state != "running" for item in current_resources.containers)
        return OperationsReport(generated_at=current_resources.observed_at, host_summary=f"{host.hostname}: CPU {host.cpu_percent if host.cpu_percent is not None else 'unavailable'}%, memory {host.memory_used_bytes} of {host.memory_total_bytes} bytes, load {host.load_1m if host.load_1m is not None else 'unavailable'}.", container_count=len(current_resources.containers), unhealthy_count=unhealthy, active_incident_count=active, resource_usage=current_resources.usage)

    def conversation_thread_id(self, conversation_id: str) -> str | None:
        return self._app_server.thread_id_for(conversation_id) if self._app_server else None

    async def answer(
        self,
        question: str,
        on_event: Callable[[dict[str, object]], Awaitable[None]] | None = None,
        *,
        conversation_id: str = "legacy",
        codex_thread_id: str | None = None,
    ) -> AgentMessageResponse:
        if self._app_server is not None and self._app_server.available:
            answer = await self._app_server.answer(
                question,
                "Use Nightwatch tools to collect the evidence required by the question.",
                on_event=on_event,
                conversation_id=conversation_id,
                stored_thread_id=codex_thread_id,
            )
            if answer:
                self._last_provider_success_at = datetime.now(UTC)
                return AgentMessageResponse(answer=answer, suggested_questions=["Which containers belong to a project?", "What is unhealthy across the stack?", "Show routes and dependencies.", "Check deployment readiness."], activity=[])
        return await self._local_evidence_answer(question, on_event)

    async def _local_evidence_answer(self, question: str, on_event: Callable[[dict[str, object]], Awaitable[None]] | None) -> AgentMessageResponse:
        if self._tool_broker is None:
            return AgentMessageResponse(answer="Nightwatch's typed tool broker is unavailable, so I cannot safely answer that question.")
        project_match = re.search(r"(?:my|the)\s+(.+?)\s+project\b", question, flags=re.IGNORECASE)
        if project_match:
            requested = project_match.group(1).strip()
            if on_event:
                await on_event({"type": "tool", "tool": "nw_find_project_containers", "status": "running", "arguments": {"project": requested}})
            data = await self._tool_broker.execute("nw_find_project_containers", {"project": requested})
            if on_event:
                await on_event({"type": "tool", "tool": "nw_find_project_containers", "status": "completed", "result": data})
            matches = data.get("matches")
            if isinstance(matches, list) and matches:
                containers = [container for match in matches if isinstance(match, dict) for container in match.get("containers", []) if isinstance(container, dict)]
                names = [str(container.get("name")) for container in containers]
                return AgentMessageResponse(answer=f"## {requested} project\n\nObserved containers: " + ", ".join(f"`{name}`" for name in names) + ".", findings=[AgentFinding(label="Matched containers", value=str(len(names)), detail="Dokploy/Compose project mapping")], citations=[AgentCitation(resource_id="topology:projects", source="topology", observed_at=datetime.now(UTC), summary=f"Matched project {requested} to {', '.join(names)}.")])
            return AgentMessageResponse(answer=f"I could not find an observed Dokploy or Compose project matching **{requested}**. I will not guess from container names.", citations=[AgentCitation(resource_id="topology:projects", source="topology", observed_at=datetime.now(UTC), summary="No project mapping matched.")])
        topology = await self._tool_broker.execute("nw_get_topology", {})
        return AgentMessageResponse(answer="Codex app-server is unavailable, so this is a local evidence-only answer. Ask about a specific project, route, incident, or deployment for a precise lookup.", citations=[AgentCitation(resource_id="topology:local", source="topology", observed_at=datetime.now(UTC), summary=f"{topology.get('resources', 0)} observed resources and {topology.get('connections', 0)} connections.")])
