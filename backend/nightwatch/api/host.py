from typing import cast

from fastapi import APIRouter, Request

from nightwatch.models.host_api import ManagedHostResponse
from nightwatch.services.host_service import HostService

router = APIRouter(prefix="/host", tags=["host"])


def service(request: Request) -> HostService:
    return cast(HostService, request.app.state.host_service)


@router.get("", response_model=ManagedHostResponse)
async def get_host(request: Request) -> ManagedHostResponse:
    return await service(request).get_host(publish_event=False)


@router.get("/capabilities", response_model=list[str])
async def get_capabilities(request: Request) -> list[str]:
    return (await service(request).get_host(publish_event=False)).capabilities


@router.get("/metrics", response_model=ManagedHostResponse)
async def get_metrics(request: Request) -> ManagedHostResponse:
    return await service(request).get_host(publish_event=False)
