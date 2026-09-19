from typing import cast

from fastapi import APIRouter, Request

from nightwatch.models.topology_api import TopologySnapshot
from nightwatch.services.topology_service import TopologyService

router = APIRouter(prefix="/topology", tags=["topology"])


@router.get("", response_model=TopologySnapshot)
async def get_topology(request: Request) -> TopologySnapshot:
    # A read must not emit TOPOLOGY_UPDATED: doing so makes subscribed dashboards refetch forever.
    return await cast(TopologyService, request.app.state.topology_service).snapshot(publish_event=False)
