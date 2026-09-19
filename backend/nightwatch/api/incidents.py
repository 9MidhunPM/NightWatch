import asyncio
from hmac import compare_digest
from typing import Any, cast

from fastapi import APIRouter, Header, HTTPException, Request, status

from nightwatch.config import Settings
from nightwatch.models.incident_api import ApprovalRequest, IncidentResponse
from nightwatch.remediation.execution import RepairExecutionError, RepairExecutionService
from nightwatch.services.incident_service import IncidentService

router = APIRouter(prefix="/incidents", tags=["incidents"])


def service(request: Request) -> IncidentService:
    return cast(IncidentService, request.app.state.incident_service)


def settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def executor(request: Request) -> RepairExecutionService:
    return cast(RepairExecutionService, request.app.state.repair_execution_service)


def investigator(request: Request) -> Any:
    return request.app.state.investigator_service


@router.get("", response_model=list[IncidentResponse])
async def get_incidents(request: Request) -> list[IncidentResponse]:
    return await service(request).list_incidents()


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(request: Request, incident_id: str) -> IncidentResponse:
    incident = await service(request).get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident was not found.")
    return incident


@router.post("/{incident_id}/investigate", status_code=status.HTTP_202_ACCEPTED)
async def investigate_incident(request: Request, incident_id: str, authorization: str | None = Header(default=None)) -> dict[str, str]:
    configured_token = settings(request).frontend_token
    forwarded = request.headers.get("x-nightwatch-frontend")
    if configured_token is None or forwarded != configured_token.get_secret_value():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
    service = investigator(request)
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Investigation is unavailable.")
    service.start(incident_id)
    return {"status": "INVESTIGATION_REQUESTED"}


@router.post("/repair-plans/{plan_id}/approval", response_model=IncidentResponse)
async def approve_repair_plan(
    request: Request,
    plan_id: str,
    payload: ApprovalRequest,
    authorization: str | None = Header(default=None),
) -> IncidentResponse:
    configured_token = settings(request).operator_token
    if configured_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operator approval is not configured.",
        )
    expected = f"Bearer {configured_token.get_secret_value()}"
    if authorization is None or not compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
    incident = await service(request).record_approval(
        plan_id,
        plan_version=payload.plan_version,
        decision=payload.decision,
        actor="operator",
    )
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repair plan is stale, unavailable, or already decided.",
        )
    if payload.decision == "APPROVED":
        asyncio.create_task(executor(request).execute(plan_id), name=f"nightwatch-repair-{plan_id}")
    return incident


@router.post("/repair-actions/{action_id}/rollback")
async def rollback_repair_action(
    request: Request, action_id: str, authorization: str | None = Header(default=None)
) -> dict[str, str]:
    configured_token = settings(request).operator_token
    expected = f"Bearer {configured_token.get_secret_value()}" if configured_token else ""
    if authorization is None or not configured_token or not compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")
    try:
        await executor(request).rollback(action_id)
    except RepairExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)}) from exc
    return {"status": "ROLLBACK_STARTED"}
