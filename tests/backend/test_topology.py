from datetime import UTC, datetime

from nightwatch.models.docker_api import DockerContainer, DockerInventory
from nightwatch.models.topology_api import InfrastructureNode
from nightwatch.models.traefik_api import TraefikRoute
from nightwatch.services.topology_service import TopologyService


def test_topology_maps_traefik_domain_to_its_labeled_container() -> None:
    inventory = DockerInventory(
        available=True,
        discovered_at=datetime.now(UTC),
        containers=[
            DockerContainer(
                id="proxy", name="traefik", image="traefik:v3", state="running", resource_type="REVERSE_PROXY"
            ),
            DockerContainer(id="api", name="demo-api", image="demo-api:latest", state="running"),
        ],
    )
    route = TraefikRoute(
        id="api-router", router_name="api", rule="Host(`demo.example.test`)",
        domains=["demo.example.test"], service_name="api", target_port=8000,
        container_id="api", container_name="demo-api",
    )

    snapshot = TopologyService._build(
        InfrastructureNode(id="host:local-host", type="HOST", label="host", health="HEALTHY"),
        inventory,
        [route],
    )

    assert {node.id for node in snapshot.nodes} >= {"internet", "domain:demo.example.test", "route:api-router", "container:api"}
    assert any(edge.source == "container:proxy" and edge.target == "container:api" and edge.type == "ROUTES_TO" for edge in snapshot.edges)
    assert len({node.id for node in snapshot.nodes}) == len(snapshot.nodes)
