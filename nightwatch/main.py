from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from nightwatch.api.events import router as events_router
from nightwatch.api.health import router as health_router
from nightwatch.config import Settings, get_settings
from nightwatch.events.bus import EventBus
from nightwatch.events.models import RealtimeEvent
from nightwatch.security.access import RealtimeTicketRegistry, valid_frontend_token
from nightwatch.storage.database import create_database, verify_database


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine, session_factory = create_database(active_settings.database_url)
        app.state.database_engine = engine
        app.state.session_factory = session_factory
        await verify_database(engine)

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(active_settings.heartbeat_interval_seconds)
                await app.state.event_bus.publish(RealtimeEvent(payload={"source": "control-plane"}))

        heartbeat_task = asyncio.create_task(heartbeat(), name="nightwatch-heartbeat")
        try:
            yield
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            await engine.dispose()

    app = FastAPI(
        title=active_settings.application_name,
        version=active_settings.version,
        lifespan=lifespan,
        docs_url=None if active_settings.environment == "production" else "/docs",
        redoc_url=None if active_settings.environment == "production" else "/redoc",
        openapi_url=None if active_settings.environment == "production" else "/openapi.json",
    )
    app.state.settings = active_settings
    app.state.event_bus = EventBus(active_settings.event_queue_size)
    app.state.realtime_tickets = RealtimeTicketRegistry()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-Request-ID", "X-Nightwatch-Frontend"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        response: Response
        requires_frontend_auth = (
            active_settings.environment == "production" or active_settings.frontend_token is not None
        )
        if requires_frontend_auth and request.url.path != "/api/health":
            expected = active_settings.frontend_token.get_secret_value() if active_settings.frontend_token else None
            if not valid_frontend_token(request.headers.get("x-nightwatch-frontend"), expected):
                response = error_response(
                    request,
                    "UNAUTHORIZED",
                    "Frontend authorization is required.",
                    status.HTTP_401_UNAUTHORIZED,
                )
                response.headers["X-Request-ID"] = request_id
                return response
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(events_router, prefix="/api")
    app.include_router(health_router, prefix="/api")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return error_response(request, "VALIDATION_ERROR", "Request validation failed.", 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(request, "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR", str(exc.detail), exc.status_code)

    return app


def error_response(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": None,
            "retryable": status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR,
            "request_id": getattr(request.state, "request_id", "unknown"),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


app = create_app()
