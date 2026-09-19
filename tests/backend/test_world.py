import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from nightwatch.adapters.beszel import BeszelContainer, BeszelContainerSnapshot
from nightwatch.adapters.domain_probe import probe_domain, public_address
from nightwatch.models.world import (
    DomainCheck,
    WorldProject,
    WorldResource,
    WorldSnapshot,
)
from nightwatch.services.world_service import (
    WorldService,
    aggregate_health,
    aggregate_project_health,
    parse_bytes,
)


def test_public_destination_boundary():
    for address in [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "224.0.0.1",
    ]:
        assert not public_address(address)
    assert public_address("1.1.1.1")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (200, "HEALTHY"),
        (401, "PROTECTED"),
        (403, "PROTECTED"),
        (404, "DEGRADED"),
        (503, "UNHEALTHY"),
    ],
)
def test_domain_status_classification(code, expected):
    async def run():
        with patch(
            "nightwatch.adapters.domain_probe._request",
            AsyncMock(return_value=(code, None)),
        ):
            assert (await probe_domain("https://example.com")).state == expected

    asyncio.run(run())


def test_redirect_is_validated_and_bounded():
    async def run():
        with patch(
            "nightwatch.adapters.domain_probe._request",
            AsyncMock(side_effect=[(302, "http://127.0.0.1/"), ValueError("blocked")]),
        ):
            result = await probe_domain("https://example.com")
            assert result.state == "UNKNOWN"
        with patch(
            "nightwatch.adapters.domain_probe._request",
            AsyncMock(return_value=(302, "/again")),
        ) as request:
            assert (await probe_domain("https://example.com")).state == "DEGRADED"
            assert request.await_count == 4

    asyncio.run(run())


def test_outage_threshold_and_two_check_recovery():
    async def run():
        incidents = SimpleNamespace(
            report_failure=AsyncMock(return_value=SimpleNamespace(id="incident-1")),
            report_recovery=AsyncMock(),
        )
        world = WorldService(None, None, None, incidents, None)
        check = DomainCheck(url="https://example.com")
        with patch(
            "nightwatch.services.world_service.probe_domain",
            AsyncMock(side_effect=lambda url: DomainCheck(url=url, state="UNHEALTHY")),
        ):
            check = await world.observe(check)
            assert check.state == "DEGRADED" and check.failures == 1
            check = await world.observe(check)
            assert check.failures == 2
            check = await world.observe(check)
            assert check.state == "UNHEALTHY" and check.incident_id == "incident-1"
            check = await world.observe(check)
            assert incidents.report_failure.await_count == 1
        # Persist/restore serialization must preserve counters and incident association.
        check = DomainCheck.model_validate_json(check.model_dump_json())
        with patch(
            "nightwatch.services.world_service.probe_domain",
            AsyncMock(side_effect=lambda url: DomainCheck(url=url, state="HEALTHY")),
        ):
            check = await world.observe(check)
            assert check.state == "DEGRADED" and check.incident_id
            check = await world.observe(check)
            assert check.state == "HEALTHY" and check.incident_id is None
            incidents.report_recovery.assert_awaited_once()

    asyncio.run(run())


def test_runtime_health_is_not_hidden_by_an_unresolved_domain_and_network_is_not_dependency():
    assert aggregate_health(["HEALTHY", "UNKNOWN"]) == "HEALTHY"
    assert aggregate_health(["HEALTHY", "UNHEALTHY"]) == "UNHEALTHY"
    resource = WorldResource(
        id="app:1",
        name="web",
        kind="application",
        project_id="p",
        environment="prod",
        networks=["shared"],
    )
    snapshot = WorldSnapshot(
        generated_at=datetime.now(UTC),
        projects=[WorldProject(id="p", name="Project", resources=[resource])],
    )
    edges = WorldService.connections(snapshot)
    assert len(edges) == 1 and edges[0].kind == "MEMBER_OF"


def test_partial_project_coverage_does_not_hide_known_health():
    assert aggregate_project_health(["HEALTHY", "UNKNOWN"]) == "DEGRADED"
    assert aggregate_project_health(["HEALTHY", "UNHEALTHY", "UNKNOWN"]) == "UNHEALTHY"
    assert aggregate_project_health(["UNKNOWN", "UNKNOWN"]) == "UNKNOWN"
    assert aggregate_project_health(["UNAVAILABLE", "UNAVAILABLE"]) == "UNAVAILABLE"


def test_dokploy_human_byte_units_are_normalized():
    assert parse_bytes("306.4MiB") == 321_283_686
    assert parse_bytes("1.25GB") == 1_250_000_000
    assert parse_bytes("not-a-size") is None


def test_beszel_runtime_is_authoritative_when_direct_docker_has_no_match():
    class Beszel:
        async def containers(self):
            observed_at = datetime.now(UTC)
            return BeszelContainerSnapshot(
                configured=True,
                available=True,
                stale=False,
                message=None,
                system_id="system-1",
                observed_at=observed_at,
                containers=[BeszelContainer(
                    id="container-1",
                    name="prism-api-hammpv.1.task",
                    status="Up 2 minutes",
                    health=2,
                    cpu_percent=0.11,
                    memory_used_bytes=round(306.4 * 1024**2),
                    network_bytes=786_000_000,
                    image=None,
                    observed_at=observed_at,
                    stale=False,
                )],
            )

    class Docker:
        async def inventory(self, publish_event=False):
            return SimpleNamespace(containers=[], discovered_at=datetime.now(UTC))

    async def run():
        resource = WorldResource(
            id="dokploy:application:prism",
            name="prism-api",
            kind="application",
            project_id="prism",
            environment="production",
            app_name="prism-api-hammpv",
            deployment_state="done",
        )
        snapshot = WorldSnapshot(
            generated_at=datetime.now(UTC),
            projects=[WorldProject(id="prism", name="PRISM", resources=[resource])],
        )
        service = WorldService(None, None, Docker(), None, None, beszel=Beszel())
        await service.runtime(snapshot)
        assert resource.health == "HEALTHY"
        assert resource.runtime_state == "1 observed replica"
        assert resource.metrics is not None
        assert resource.metrics.memory_used_bytes == round(306.4 * 1024**2)
        assert resource.metrics.network_rx_bytes == 786_000_000

    asyncio.run(run())


def test_discovery_includes_empty_projects_and_databases_without_secrets():
    class Dokploy:
        configured = True

        @staticmethod
        def _data(value):
            return value

        @staticmethod
        def _projects(value):
            return value

        async def _async_request(self, method, path, **kwargs):
            if path == "/api/project.all":
                return [
                    {"projectId": "empty", "name": "Empty", "environments": []},
                    {
                        "projectId": "p",
                        "name": "Production",
                        "environments": [
                            {
                                "name": "production",
                                "postgres": [{"postgresId": "db"}],
                                "applications": [{"applicationId": "a", "name": "Web"}],
                            }
                        ],
                    },
                ]
            if path == "/api/postgres.one":
                return {
                    "name": "Database",
                    "appName": "database-app",
                    "password": "DO-NOT-EXPOSE",
                    "env": "SECRET=NO",
                }
            if path == "/api/application.one":
                return {
                    "name": "Web",
                    "appName": "web-app",
                    "env": "SECRET=NO",
                    "domains": [{"host": "example.com", "https": True}],
                }
            return []

    async def run():
        service = WorldService(None, Dokploy(), None, None, None)
        projects = await service.discover()
        assert len(projects) == 2
        assert len(projects[0].resources) == 0
        assert {r.kind for r in projects[1].resources} == {"application", "postgres"}
        assert "DO-NOT-EXPOSE" not in str(projects) and "SECRET=NO" not in str(projects)

    asyncio.run(run())
