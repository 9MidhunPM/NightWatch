from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nightwatch.config import Settings
from nightwatch.main import create_app
from nightwatch.storage.database import Base, create_database


async def create_schema(settings: Settings) -> None:
    engine, _ = create_database(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.mark.anyio
async def test_health_endpoint_returns_control_plane_identity(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'health.db'}")
    await create_schema(settings)
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.json()["status"] == "ok"
    assert response.json()["application"] == "NightWatch"
    assert response.json()["version"] == "0.1.0"
    assert response.json()["timestamp"].endswith("Z")


@pytest.mark.anyio
async def test_application_startup_creates_sqlite_file(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "startup.db"
    settings = Settings(database_url=f"sqlite+aiosqlite:///{database_path}")
    await create_schema(settings)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert database_path.exists()


@pytest.mark.anyio
async def test_not_found_uses_structured_error_envelope(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'errors.db'}")
    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/missing")

    assert response.status_code == 404
    assert response.headers["x-request-id"]
    assert response.json().keys() == {
        "code",
        "message",
        "details",
        "retryable",
        "request_id",
        "timestamp",
    }
    assert response.json()["code"] == "NOT_FOUND"
