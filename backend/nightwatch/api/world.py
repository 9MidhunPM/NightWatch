from typing import cast

from fastapi import APIRouter, Request

from nightwatch.models.world import WorldSnapshot
from nightwatch.services.world_service import WorldService

router = APIRouter(tags=["world"])


@router.get("/world", response_model=WorldSnapshot)
async def world(request: Request) -> WorldSnapshot:
    return cast(WorldService, request.app.state.world_service).current
