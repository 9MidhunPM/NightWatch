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
async def test_host_endpoint_reports_the_local_managed_host(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'host.db'}")
    await create_schema(settings)
    app = create_app(settings)

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/host")
        capabilities_response = await client.get("/api/host/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "local-host"
    assert payload["hostname"]
    assert {"HTTP_PROBE", "TCP_PROBE", "DNS"}.issubset(payload["capabilities"])
    assert "endpoint" not in payload
    assert capabilities_response.json() == payload["capabilities"]
