from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from nightwatch.api.deployments import _approval_authorized
from nightwatch.models.deployment_api import DokployActionApprovalRequest, DokployActionRequest
from nightwatch.services.dokploy_action_service import DokployActionService

router = APIRouter(prefix="/dokploy/actions", tags=["dokploy-actions"])


def service(request: Request) -> DokployActionService:
    return cast(DokployActionService, request.app.state.dokploy_action_service)


@router.get("")
async def plans(request: Request, conversation_id: str | None = Query(default=None, max_length=36)) -> list[dict[str, object]]:
    return await service(request).plans(conversation_id)


@router.post("")
async def create(request: Request, payload: DokployActionRequest, authorization: str | None = Header(default=None)) -> dict[str, object]:
    if not _approval_authorized(request, authorization):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    try:
        return await service(request).create_plan(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{plan_id}/approval")
async def approve(request: Request, plan_id: str, payload: DokployActionApprovalRequest, authorization: str | None = Header(default=None)) -> dict[str, object]:
    if not _approval_authorized(request, authorization):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    try:
        plan = await service(request).approve(plan_id, payload.version, payload.decision, payload.confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if plan is None:
        raise HTTPException(status_code=409, detail="Action plan is stale, unavailable, or already decided.")
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def remove(request: Request, plan_id: str, authorization: str | None = Header(default=None)):
    if not _approval_authorized(request, authorization) or not await service(request).delete_plan(plan_id):
        raise HTTPException(status_code=409, detail="Only terminal action plans can be deleted.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
