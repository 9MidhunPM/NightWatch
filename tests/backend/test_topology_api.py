from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request

from nightwatch.api.topology import get_topology
from nightwatch.models.topology_api import TopologySnapshot


class TopologyServiceSpy:
    def __init__(self) -> None:
        self.publish_event: bool | None = None

    async def snapshot(self, *, publish_event: bool = False) -> TopologySnapshot:
        self.publish_event = publish_event
        return TopologySnapshot(available=True, generated_at=datetime.now(UTC))


@pytest.mark.anyio
async def test_topology_read_does_not_publish_a_topology_updated_event() -> None:
    service = TopologyServiceSpy()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(topology_service=service)))

    response = await get_topology(cast(Request, request))

    assert response.available is True
    assert service.publish_event is False
