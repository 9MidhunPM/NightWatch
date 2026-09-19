from datetime import UTC, datetime
from pathlib import Path

import pytest

from nightwatch.events.bus import EventBus
from nightwatch.models.docker_api import DockerContainer, DockerInventory, DockerPort
from nightwatch.models.topology_api import InfrastructureNode, TopologySnapshot
from nightwatch.models.traefik_api import TraefikRoute
from nightwatch.policy import PolicyDecision, PolicyEngine
from nightwatch.remediation.execution import ComposeRouteSource, RepairExecutionError
from nightwatch.remediation.service import RemediationService
from nightwatch.services.incident_service import IncidentService
from nightwatch.storage.database import Base, create_database


def test_policy_requires_approval_for_route_patch_and_denies_destructive_actions() -> None:
    policy = PolicyEngine()
    assert policy.evaluate("TRAEFIK_PATCH_SERVICE_PORT", protected=False).decision == (
        PolicyDecision.REQUIRE_APPROVAL
    )
    assert policy.evaluate("DELETE_VOLUME", protected=False).decision == PolicyDecision.DENY
    assert policy.evaluate("TRAEFIK_PATCH_SERVICE_PORT", protected=True).decision == (
        PolicyDecision.DENY
    )


def test_unflagged_compose_service_cannot_mutate(tmp_path: Path) -> None:
    compose = tmp_path / "demo.yml"
    compose.write_text(
        "services:\n  api:\n    labels:\n      traefik.http.services.demo.loadbalancer.server.port: '9999'\n",
        encoding="utf-8",
    )
    source = ComposeRouteSource(compose, "demo", "api")
    with pytest.raises(RepairExecutionError, match="explicitly flagged") as exc:
        source.patch_port("traefik.http.services.demo.loadbalancer.server.port", "9999", "8000")
    assert exc.value.code == "TARGET_PROTECTED"


class _Topology:
    async def snapshot(self, *, publish_event: bool) -> TopologySnapshot:
        return TopologySnapshot(
            available=True,
            generated_at=datetime.now(UTC),
            nodes=[
                InfrastructureNode(
                    id="container:api",
                    type="SERVICE",
                    label="demo-api",
                    health="HEALTHY",
                )
            ],
        )

    async def traefik_routes(self) -> list[TraefikRoute]:
        return [
            TraefikRoute(
                id="proxy:demo",
                router_name="demo",
                rule="Host(`demo.test`)",
                service_name="demo-api",
                target_port=9999,
                container_id="api",
                container_name="demo-api",
            )
        ]


class _Docker:
    async def inventory(self, *, publish_event: bool) -> DockerInventory:
        return DockerInventory(
            available=True,
            discovered_at=datetime.now(UTC),
            containers=[
                DockerContainer(
                    id="api",
                    name="demo-api",
                    image="demo-api:latest",
                    state="running",
                    ports=[DockerPort(internal="8000/tcp")],
                )
            ],
        )


@pytest.mark.anyio
async def test_confirmed_route_mismatch_creates_one_approval_gated_port_change(
    tmp_path: Path,
) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'repair.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    incidents = IncidentService(sessions, EventBus(10))
    incident = await incidents.report_failure(
        key="http:https://demo.test",
        title="Public route unavailable",
        severity="CRITICAL",
        trigger={"type": "HTTP_FAILURE"},
        affected_resource_ids=["route:proxy:demo", "domain:demo.test"],
        observation_summary="Public endpoint returned HTTP 502.",
        observation_data={},
    )
    await incidents.begin_investigation(incident.id)
    evidence_id = await incidents.record_tool_evidence(
        incident.id,
        tool="traefik_get_routes",
        resource_id="route:proxy:demo",
        summary="Traefik targets port 9999 while the API exposes 8000.",
        data={
            "routes": [
                {"id": "proxy:demo", "container_id": "api", "target_port": 9999}
            ]
        },
        usable=True,
    )
    assert evidence_id is not None
    container_evidence_id = await incidents.record_tool_evidence(
        incident.id,
        tool="docker_inspect_container",
        resource_id="container:api",
        summary="API container is running and exposes port 8000.",
        data={"state": "running", "ports": [{"internal": "8000/tcp"}]},
        usable=True,
    )
    probe_evidence_id = await incidents.record_tool_evidence(
        incident.id,
        tool="http_probe",
        resource_id="url:http://demo-api:8000/health",
        summary="Internal API health probe returned HTTP 200.",
        data={"reachable": True, "status_code": 200},
        usable=True,
    )
    confirmed = await incidents.apply_investigation_outcome(
        incident.id,
        summary="Route target mismatch confirmed.",
        confirmed_title="Reverse proxy target port mismatch",
        next_step="Create a minimal repair plan.",
        hypotheses=[
            {
                "title": "Reverse proxy target port mismatch",
                "description": "The configured Traefik target differs from the API port.",
                "status": "CONFIRMED",
                "supporting_evidence_ids": [evidence_id, container_evidence_id, probe_evidence_id],
                "contradicting_evidence_ids": [],
                "related_resource_ids": ["route:proxy:demo", "container:api"],
            }
        ],
    )
    assert confirmed is not None
    await RemediationService(sessions, incidents, _Docker(), _Topology()).plan_for_incident(incident.id)
    planned = await incidents.get_incident(incident.id)
    assert planned is not None
    assert planned.repair_plan is not None
    assert planned.repair_plan.policy_decision == "REQUIRE_APPROVAL"
    assert "route:proxy:demo" in planned.repair_plan.blast_radius_resource_ids
    assert [(change.from_value, change.to_value) for change in planned.repair_plan.changes] == [
        ("9999", "8000")
    ]
    approved = await incidents.record_approval(
        planned.repair_plan.id,
        plan_version=planned.repair_plan.version,
        decision="APPROVED",
        actor="test-operator",
    )
    assert approved is not None
    assert approved.repair_plan is not None
    assert approved.repair_plan.status == "APPROVED"
    await engine.dispose()
