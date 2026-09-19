from __future__ import annotations

import asyncio
import logging
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

from nightwatch.adapters.beszel import BeszelAdapter
from nightwatch.adapters.docker import DockerAdapter
from nightwatch.adapters.dokploy import DokployAdapter
from nightwatch.adapters.host import LocalHostAdapter
from nightwatch.adapters.traefik import TraefikAdapter
from nightwatch.agents.app_server import CodexAppServer
from nightwatch.agents.investigator import InvestigatorService
from nightwatch.agents.operations_tools import OperationsToolBroker
from nightwatch.api.chaos import router as chaos_router
from nightwatch.api.deployments import router as deployments_router
from nightwatch.api.docker import router as docker_router
from nightwatch.api.events import router as events_router
from nightwatch.api.health import router as health_router
from nightwatch.api.host import router as host_router
from nightwatch.api.incidents import router as incidents_router
from nightwatch.api.operations import router as operations_router
from nightwatch.api.topology import router as topology_router
from nightwatch.chaos.service import ChaosService
from nightwatch.config import Settings, get_settings
from nightwatch.events.bus import EventBus
from nightwatch.events.models import RealtimeEvent
from nightwatch.logging import configure_logging
from nightwatch.remediation.execution import ComposeRouteSource, RepairExecutionService
from nightwatch.remediation.service import RemediationService
from nightwatch.security.access import RealtimeTicketRegistry, valid_frontend_token
from nightwatch.services.beszel_service import BeszelService
from nightwatch.services.conversation_service import ConversationService
from nightwatch.services.deployment_service import DeploymentService
from nightwatch.services.docker_service import DockerService
from nightwatch.services.host_service import HostService
from nightwatch.services.incident_service import IncidentService
from nightwatch.services.monitoring_service import MonitoringService
from nightwatch.services.operations_service import OperationsService
from nightwatch.services.topology_service import TopologyService
from nightwatch.storage.database import create_database, verify_database
from nightwatch.tools.investigation_tools import InvestigationToolRegistry

logger = logging.getLogger("nightwatch.control_plane")


async def heartbeat_loop(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    while True:
        await asyncio.sleep(settings.heartbeat_interval_seconds)
        await app.state.event_bus.publish(RealtimeEvent(payload={"source": "control-plane"}))


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine, session_factory = create_database(active_settings.database_url)
        app.state.database_engine = engine
        app.state.session_factory = session_factory
        await verify_database(engine)
        docker_adapter = DockerAdapter()
        app.state.host_service = HostService(
            session_factory,
            app.state.event_bus,
            LocalHostAdapter(docker_adapter),
            active_settings.environment,
        )
        app.state.docker_service = DockerService(docker_adapter, app.state.event_bus)
        app.state.beszel_service = BeszelService(
            BeszelAdapter(
                active_settings.beszel_url,
                active_settings.beszel_email,
                active_settings.beszel_password.get_secret_value() if active_settings.beszel_password else None,
                active_settings.beszel_system_id,
            )
        )
        app.state.incident_service = IncidentService(session_factory, app.state.event_bus)
        app.state.codex_app_server = CodexAppServer(
            active_settings.codex_app_server_command,
            active_settings.codex_api_key.get_secret_value() if active_settings.codex_api_key else None,
            timeout_seconds=active_settings.codex_app_server_timeout_seconds,
        ) if active_settings.codex_app_server_enabled else None
        app.state.operations_service = OperationsService(
            app.state.docker_service, app.state.host_service, app.state.incident_service,
            api_key=active_settings.codex_api_key.get_secret_value() if active_settings.codex_api_key else None,
            model=active_settings.codex_model,
            app_server=app.state.codex_app_server,
        )
        traefik_adapter = TraefikAdapter()
        dokploy_adapter = DokployAdapter(
            active_settings.dokploy_url,
            active_settings.dokploy_api_key.get_secret_value()
            if active_settings.dokploy_api_key
            else None,
        )
        app.state.topology_service = TopologyService(
            app.state.host_service,
            app.state.docker_service,
            traefik_adapter,
            app.state.event_bus,
            app.state.incident_service,
            dokploy_adapter,
        )
        app.state.operations_service.set_topology(app.state.topology_service)
        app.state.deployment_service = DeploymentService(
            session_factory,
            dokploy_adapter,
            github_id=active_settings.dokploy_github_id,
            github_read_token=(active_settings.github_read_token.get_secret_value() if active_settings.github_read_token else None),
            secret_catalog=(
                active_settings.deployment_secret_catalog.get_secret_value()
                if active_settings.deployment_secret_catalog
                else None
            ),
            app_server_enabled=active_settings.codex_app_server_enabled,
        )
        app.state.operations_service.set_deployment(app.state.deployment_service)
        tool_broker = OperationsToolBroker(
            app.state.topology_service,
            app.state.incident_service,
            app.state.deployment_service,
        )
        app.state.operations_service.set_tool_broker(tool_broker)
        app.state.conversation_service = ConversationService(session_factory, app.state.operations_service, app.state.deployment_service)
        if app.state.codex_app_server is not None:
            app.state.codex_app_server.configure_tools(tool_broker.definitions(), tool_broker.execute)
            await app.state.codex_app_server.start()
            logger.info(
                "codex app-server status available=%s tool_count=%s",
                app.state.codex_app_server.available,
                len(tool_broker.definitions()),
            )
        app.state.remediation_service = RemediationService(
            session_factory,
            app.state.incident_service,
            app.state.docker_service,
            app.state.topology_service,
        )
        demo_source = ComposeRouteSource(
            active_settings.demo_compose_file,
            active_settings.demo_compose_project,
            active_settings.demo_compose_service,
        )
        app.state.repair_execution_service = RepairExecutionService(
            session_factory, app.state.event_bus, app.state.docker_service, app.state.topology_service,
            demo_source,
            active_settings.demo_url or active_settings.public_demo_url, active_settings.demo_internal_health_url,
            active_settings.monitor_timeout_seconds,
        )
        app.state.chaos_service = ChaosService(demo_source, app.state.event_bus, active_settings.demo_expected_port)
        app.state.investigator_service = InvestigatorService(
            app.state.incident_service,
            InvestigationToolRegistry(
                app.state.host_service,
                app.state.docker_service,
                app.state.topology_service,
                traefik_adapter,
                timeout_seconds=active_settings.monitor_timeout_seconds,
            ),
            api_key=(
                active_settings.codex_api_key.get_secret_value()
                if active_settings.codex_api_key
                else None
            ),
            model=active_settings.codex_model,
            max_tool_calls=active_settings.investigator_max_tool_calls,
            timeout_seconds=active_settings.investigator_timeout_seconds,
            on_root_cause_confirmed=app.state.remediation_service.plan_for_incident,
        )
        app.state.monitoring_service = MonitoringService(
            app.state.docker_service,
            app.state.topology_service,
            app.state.incident_service,
            app.state.event_bus,
            demo_url=active_settings.demo_url or active_settings.public_demo_url,
            timeout_seconds=active_settings.monitor_timeout_seconds,
            failure_threshold=active_settings.monitor_failure_threshold,
            investigator_service=(
                app.state.investigator_service if active_settings.investigator_enabled else None
            ),
        )
        await app.state.host_service.refresh(publish_event=False)
        await app.state.remediation_service.reconcile_confirmed_plans()
        heartbeat_task = asyncio.create_task(heartbeat_loop(app), name="nightwatch-heartbeat")
        monitoring_task = (
            asyncio.create_task(
                app.state.monitoring_service.run_forever(active_settings.monitor_interval_seconds),
                name="nightwatch-monitoring",
            )
            if active_settings.monitoring_enabled
            else None
        )
        logger.info("control plane started", extra={"result": "ready"})
        try:
            yield
        finally:
            heartbeat_task.cancel()
            if monitoring_task:
                monitoring_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            if monitoring_task:
                with suppress(asyncio.CancelledError):
                    await monitoring_task
            if app.state.codex_app_server is not None:
                await app.state.codex_app_server.close()
            await engine.dispose()
            logger.info("control plane stopped", extra={"result": "stopped"})

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
        allow_headers=["Accept", "Content-Type", "X-Request-ID"],
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
            expected = (
                active_settings.frontend_token.get_secret_value()
                if active_settings.frontend_token
                else None
            )
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

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
        return error_response(request, "VALIDATION_ERROR", "Request validation failed.", 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed."
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        response = error_response(request, code, message, exc.status_code)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled API error",
            exc_info=exc,
            extra={"request_id": getattr(request.state, "request_id", "unknown")},
        )
        return error_response(request, "INTERNAL_ERROR", "An internal error occurred.", 500)

    app.include_router(health_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(host_router, prefix="/api")
    app.include_router(incidents_router, prefix="/api")
    app.include_router(docker_router, prefix="/api")
    app.include_router(topology_router, prefix="/api")
    app.include_router(chaos_router, prefix="/api")
    app.include_router(operations_router, prefix="/api")
    app.include_router(deployments_router, prefix="/api")
    return app


def error_response(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": None,
            "retryable": status_code >= 500,
            "request_id": getattr(request.state, "request_id", "unknown"),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


app = create_app()
