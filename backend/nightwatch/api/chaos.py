from hmac import compare_digest
from typing import cast

from fastapi import APIRouter, Header, HTTPException, Request, status

from nightwatch.chaos.service import ChaosService
from nightwatch.config import Settings
from nightwatch.remediation.execution import RepairExecutionError

router = APIRouter(prefix="/chaos", tags=["chaos"])


def service(request: Request) -> ChaosService:
    return cast(ChaosService, request.app.state.chaos_service)


def _require_operator(request: Request, authorization: str | None) -> None:
    settings = cast(Settings, request.app.state.settings)
    token = settings.operator_token.get_secret_value() if settings.operator_token else ""
    if not token or authorization is None or not compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")


@router.get("")
async def get_chaos_status(request: Request) -> dict[str, object]:
    return service(request).status()


@router.post("/route-mismatch", status_code=status.HTTP_202_ACCEPTED)
async def inject_route_mismatch(
    request: Request, authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _require_operator(request, authorization)
    try:
        await service(request).inject_route_mismatch()
    except RepairExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)}) from exc
    return {"status": "INJECTED"}


@router.post("/reset", status_code=status.HTTP_202_ACCEPTED)
async def reset_demo(request: Request, authorization: str | None = Header(default=None)) -> dict[str, str]:
    _require_operator(request, authorization)
    try:
        await service(request).reset()
    except RepairExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)}) from exc
    return {"status": "RESET"}
