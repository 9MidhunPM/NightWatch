from __future__ import annotations

from hmac import compare_digest
from typing import cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from nightwatch.adapters.dokploy import DokployError
from nightwatch.config import Settings
from nightwatch.models.deployment_api import (
    DeploymentApprovalRequest,
    DeploymentPlanRequest,
    DeploymentPlanResponse,
    DeploymentStatusResponse,
    GithubRepository,
)
from nightwatch.services.deployment_service import DeploymentService

router = APIRouter(prefix="/deployments", tags=["deployments"])


def service(request: Request) -> DeploymentService:
    return cast(DeploymentService, request.app.state.deployment_service)


def _operator_authorized(settings: Settings, authorization: str | None) -> bool:
    token = settings.operator_token.get_secret_value() if settings.operator_token else ""
    return bool(token and authorization and compare_digest(authorization, f"Bearer {token}"))


def _approval_authorized(request: Request, authorization: str | None) -> bool:
    """Accept the private dashboard proxy as an approval authority.

    The global middleware has already fail-closed on the matching frontend token.
    Requiring a second token in the same server-side proxy made valid dashboard
    approvals fail whenever the optional operator token was absent or rotated.
    """
    active = cast(Settings, request.app.state.settings)
    frontend = active.frontend_token.get_secret_value() if active.frontend_token else ""
    forwarded = request.headers.get("x-nightwatch-frontend")
    return bool(frontend and forwarded and compare_digest(frontend, forwarded)) or _operator_authorized(active, authorization)


@router.get("/status", response_model=DeploymentStatusResponse)
async def deployment_status(request: Request) -> DeploymentStatusResponse:
    return await service(request).validated_status()


@router.get("/repositories", response_model=list[GithubRepository])
async def repositories(request: Request) -> list[GithubRepository]:
    try:
        return await service(request).repositories()
    except DokployError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GitHub repository discovery is unavailable.") from None


@router.get("/repositories/{owner}/{repository}/branches", response_model=list[str])
async def branches(request: Request, owner: str, repository: str) -> list[str]:
    try:
        return await service(request).branches(owner, repository)
    except DokployError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GitHub branch discovery is unavailable.") from None


@router.get("/plans", response_model=list[DeploymentPlanResponse])
async def plans(request: Request, conversation_id: str | None = Query(default=None, max_length=36)) -> list[DeploymentPlanResponse]:
    return await service(request).plans(conversation_id)


@router.post("/plans", response_model=DeploymentPlanResponse)
async def create_plan(
    request: Request,
    payload: DeploymentPlanRequest,
    authorization: str | None = Header(default=None),
) -> DeploymentPlanResponse:
    if not _approval_authorized(request, authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
    try:
        return await service(request).create_plan(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/plans/{plan_id}/approval", response_model=DeploymentPlanResponse)
async def approve_plan(
    request: Request,
    plan_id: str,
    payload: DeploymentApprovalRequest,
    authorization: str | None = Header(default=None),
) -> DeploymentPlanResponse:
    if not _approval_authorized(request, authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
    plan = await service(request).approve(plan_id, payload.version, payload.decision, payload.conversation_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deployment plan is stale, unavailable, or already decided.")
    return plan


@router.post("/plans/{plan_id}/retry", response_model=DeploymentPlanResponse)
async def retry_plan(request: Request, plan_id: str, authorization: str | None = Header(default=None)) -> DeploymentPlanResponse:
    if not _approval_authorized(request, authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
    plan = await service(request).retry(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a failed approved plan can be retried.")
    return plan


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(request: Request, plan_id: str, authorization: str | None = Header(default=None)) -> None:
    if not _approval_authorized(request, authorization) or not await service(request).delete_plan(plan_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only terminal deployment plans can be deleted.")


@router.delete("/project-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_plan(request: Request, plan_id: str, authorization: str | None = Header(default=None)) -> None:
    if not _approval_authorized(request, authorization) or not await service(request).delete_project_plan(plan_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only terminal project plans can be deleted.")


@router.post("/project-plans/{plan_id}/approval")
async def approve_project_plan(
    request: Request, plan_id: str, payload: DeploymentApprovalRequest, authorization: str | None = Header(default=None)
) -> dict[str, object]:
    if not _approval_authorized(request, authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator authorization is required.")
    plan = await service(request).approve_project_plan(plan_id, payload.version, payload.decision, payload.conversation_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project plan was not found or its version changed. Refresh the conversation before approving a replacement plan.")
    return plan


@router.get("/project-plans/{plan_id}")
async def get_project_plan(request: Request, plan_id: str) -> dict[str, object]:
    plan = await service(request).project_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project plan was not found.")
    return plan


@router.get("/project-plans")
async def list_project_plans(request: Request, conversation_id: str | None = Query(default=None, max_length=36)) -> list[dict[str, object]]:
    return await service(request).project_plans(conversation_id)
