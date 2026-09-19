from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from nightwatch.config import Settings
from nightwatch.main import create_app
from nightwatch.security.access import RealtimeTicketRegistry
from nightwatch.storage.database import Base, create_database


async def create_schema(settings: Settings) -> None:
    engine, _ = create_database(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


def production_settings(database_path: Path) -> Settings:
    return Settings(
        environment="production",
        database_url=f"sqlite+aiosqlite:///{database_path}",
        frontend_token="f" * 40,
        cors_origins="https://nightwatch.example.com",
        websocket_origins="https://nightwatch.example.com",
    )


def test_production_requires_frontend_token_and_exact_https_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")


@pytest.mark.anyio
async def test_operational_routes_require_frontend_token(tmp_path: Path) -> None:
    settings = production_settings(tmp_path / "access.db")
    await create_schema(settings)
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://nightwatch.example.com") as client,
    ):
        health = await client.get("/api/health")
        denied = await client.get("/api/docker/status")
        allowed = await client.get("/api/docker/status", headers={"X-Nightwatch-Frontend": "f" * 40})
        ticket_denied = await client.post("/api/realtime-ticket")
        ticket_allowed = await client.post("/api/realtime-ticket", headers={"X-Nightwatch-Frontend": "f" * 40})

    assert health.status_code == 200
    assert denied.status_code == 401
    assert denied.json()["code"] == "UNAUTHORIZED"
    assert allowed.status_code == 200
    assert ticket_denied.status_code == 401
    assert ticket_allowed.status_code == 200
    assert isinstance(ticket_allowed.json()["ticket"], str)


def test_realtime_ticket_is_single_use_and_tamper_resistant() -> None:
    registry = RealtimeTicketRegistry()
    ticket = registry.issue("s" * 40, 30)
    assert registry.consume(ticket, "s" * 40)
    assert not registry.consume(ticket, "s" * 40)
    assert not registry.consume(f"{ticket}x", "s" * 40)


def test_realtime_ticket_supports_local_development_without_production_secret() -> None:
    registry = RealtimeTicketRegistry()
    ticket = registry.issue("", 30)
    assert registry.consume(ticket, "")
