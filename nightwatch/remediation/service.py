from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.models.incident import Incident, RepairChange, RepairPlan
from nightwatch.models.incident_api import EvidenceResponse, HypothesisResponse
from nightwatch.models.topology_api import TopologySnapshot
from nightwatch.policy import PolicyEngine
from nightwatch.services.docker_service import DockerService
from nightwatch.services.incident_service import IncidentService
from nightwatch.services.topology_service import TopologyService


class RemediationService:
    """Creates an exact, non-executing repair plan from confirmed local evidence."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        incidents: IncidentService,
        docker: DockerService,
        topology: TopologyService,
    ) -> None:
        self._sessions = sessions
        self._incidents = incidents
        self._docker = docker
        self._topology = topology
        self._policy = PolicyEngine()

    async def plan_for_incident(self, incident_id: str) -> None:
        incident = await self._incidents.get_incident(incident_id)
        if incident is None or incident.state != "ROOT_CAUSE_CONFIRMED" or incident.repair_plan:
            return
        confirmed = next((item for item in incident.hypotheses if item.status == "CONFIRMED"), None)
        if confirmed is None:
            return
        snapshot = await self._topology.snapshot(publish_event=False)
        routes = await self._topology.traefik_routes()
        route_ids = [
            resource_id.removeprefix("route:")
            for resource_id in incident.affected_resource_ids
            if resource_id.startswith("route:")
        ]
        route = next((item for item in routes if item.id in route_ids), None)
        if route is None or route.target_port is None:
            return
        inventory = await self._docker.inventory(publish_event=False)
        container = next((item for item in inventory.containers if item.id == route.container_id), None)
        candidate_ports = ({
            port.internal.split("/", 1)[0]
            for port in container.ports
            if port.internal.split("/", 1)[0].isdigit()
            and int(port.internal.split("/", 1)[0]) != route.target_port
        } if container else set())
        # A port change is only safe to propose when discovery gives one unambiguous target.
        if len(candidate_ports) != 1:
            return
        correct_port = candidate_ports.pop()
        if not self._evidence_proves_port_mismatch(
            incident.evidence, confirmed, route.id, route.container_id, route.target_port, correct_port
        ):
            return
        action_type = "TRAEFIK_PATCH_SERVICE_PORT"
        protected = any(node.id == f"container:{route.container_id}" and node.protected for node in snapshot.nodes)
        policy = self._policy.evaluate(action_type, protected=protected)
        if policy.decision.value != "REQUIRE_APPROVAL":
            return
        route_resource_id = f"route:{route.id}"
        blast_radius = self._blast_radius(
            snapshot, {route_resource_id, f"container:{route.container_id}"}
        )
        async with self._sessions() as session:
            existing = await session.scalar(
                select(RepairPlan.id).where(RepairPlan.incident_id == incident_id)
            )
            if existing is not None:
                return
            plan = RepairPlan(
                incident_id=incident_id,
                title=f"Restore Traefik target for {route.router_name}",
                status="AWAITING_APPROVAL",
                target_resource_id=route_resource_id,
                reason=confirmed.description,
                evidence_ids=confirmed.supporting_evidence_ids,
                risk_level=policy.risk_level,
                blast_radius_resource_ids=blast_radius,
                expected_downtime=(
                    "No expected downtime; routing reload may briefly affect requests."
                ),
                verification_plan=[
                    "Confirm the backend container remains healthy.",
                    "Probe the public endpoint and require HTTP 200.",
                    "Confirm the original failure no longer reproduces.",
                ],
                rollback_plan=[f"Restore Traefik service port from {correct_port} to {route.target_port}."],
                policy_decision=policy.decision.value,
                policy_reason=policy.reason,
            )
            session.add(plan)
            await session.flush()
            session.add(
                RepairChange(
                    repair_plan_id=plan.id,
                    action_type=action_type,
                    target_resource_id=route_resource_id,
                    field=(
                        f"traefik.http.services.{route.service_name}."
                        "loadbalancer.server.port"
                    ),
                    from_value=str(route.target_port),
                    to_value=correct_port,
                    reversible=True,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return
        await self._incidents.record_repair_plan(
            incident_id,
            plan_id=plan.id,
            title=plan.title,
            target_resource_id=plan.target_resource_id,
            policy_decision=policy.decision.value,
            policy_reason=policy.reason,
        )

    async def reconcile_confirmed_plans(self) -> None:
        """Restore the plan-only handoff if the process restarted after confirmation."""
        async with self._sessions() as session:
            incident_ids = list(
                (
                    await session.scalars(
                        select(Incident.id)
                        .where(Incident.state == "ROOT_CAUSE_CONFIRMED")
                        .order_by(Incident.updated_at.desc())
                        .limit(20)
                    )
                ).all()
            )
        for incident_id in incident_ids:
            await self.plan_for_incident(incident_id)

    @staticmethod
    def _blast_radius(snapshot: TopologySnapshot, targets: set[str]) -> list[str]:
        related = set(targets)
        for edge in snapshot.edges:
            if edge.source in targets or edge.target in targets:
                related.update({edge.source, edge.target})
        return sorted(related)

    @staticmethod
    def _evidence_proves_port_mismatch(
        evidence: list[EvidenceResponse],
        hypothesis: HypothesisResponse,
        route_id: str,
        container_id: str,
        configured_port: int,
        candidate_port: str,
    ) -> bool:
        supporting = {item.id for item in evidence if item.id in hypothesis.supporting_evidence_ids}
        route_proven = False
        container_proven = False
        candidate_reachable = False
        for item in evidence:
            if item.id not in supporting:
                continue
            if item.source == "traefik_get_routes":
                routes = item.data.get("routes")
                if isinstance(routes, list):
                    route_proven = any(
                        isinstance(route, dict)
                        and route.get("id") == route_id
                        and route.get("container_id") == container_id
                        and route.get("target_port") == configured_port
                        for route in routes
                    )
            if item.source == "docker_inspect_container" and item.resource_id == f"container:{container_id}":
                ports = item.data.get("ports")
                container_proven = (
                    item.data.get("state") == "running"
                    and isinstance(ports, list)
                    and any(
                        isinstance(port, dict)
                        and str(port.get("internal", "")).split("/", 1)[0] == candidate_port
                        for port in ports
                    )
                )
            if item.source in {"http_probe", "tcp_probe"}:
                candidate_reachable = (
                    item.data.get("reachable") is True
                    and f":{candidate_port}" in item.resource_id
                )
        return route_proven and container_proven and candidate_reachable
