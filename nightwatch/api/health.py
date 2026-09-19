from datetime import UTC, datetime

from fastapi import APIRouter, Request

from nightwatch.models.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        application=settings.application_name,
        version=settings.version,
        timestamp=datetime.now(UTC),
    )
