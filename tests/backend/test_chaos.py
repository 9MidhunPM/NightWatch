from pathlib import Path

import pytest

from nightwatch.chaos.service import ChaosService
from nightwatch.events.bus import EventBus
from nightwatch.remediation.execution import RepairExecutionError


class DemoSource:
    path = Path("/tmp/nightwatch-demo-compose.yml")
    service = "api"

    def __init__(self, port: str = "80") -> None:
        self.port = port
        self.redeploy_count = 0

    def read_port(self, _field: str) -> str:
        return self.port

    def patch_port(self, _field: str, expected: str, replacement: str) -> None:
        if self.port != expected:
            raise RepairExecutionError("CURRENT_STATE_MISMATCH", "unexpected test state")
        self.port = replacement

    def redeploy(self) -> None:
        self.redeploy_count += 1


@pytest.mark.anyio
async def test_route_mismatch_is_bounded_and_reset_is_idempotent() -> None:
    source = DemoSource()
    service = ChaosService(source, EventBus(), expected_port=80)

    await service.inject_route_mismatch()
    assert source.port == "9"
    assert source.redeploy_count == 1

    await service.reset()
    assert source.port == "80"
    assert source.redeploy_count == 2

    await service.reset()
    assert source.redeploy_count == 2


@pytest.mark.anyio
async def test_route_mismatch_refuses_to_overwrite_an_existing_demo_fault() -> None:
    source = DemoSource(port="9")
    service = ChaosService(source, EventBus(), expected_port=80)

    with pytest.raises(RepairExecutionError, match="Reset the demo"):
        await service.inject_route_mismatch()

    assert source.port == "9"
    assert source.redeploy_count == 0


def test_chaos_status_exposes_safe_current_state() -> None:
    source = DemoSource(port="9")
    status = ChaosService(source, EventBus(), expected_port=80).status()

    assert status["state"] == "FAULT_INJECTED"
    assert status["current_port"] == "9"
    assert status["actions"] == {"inject_route_mismatch": False, "reset": True}
