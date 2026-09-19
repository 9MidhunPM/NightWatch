from typing import Self

import httpx
import pytest

from nightwatch.adapters.dokploy import DokployAdapter


@pytest.mark.anyio
async def test_deploy_accepts_an_empty_success_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyDeployClient:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def request(self, *_args: object, **_kwargs: object) -> httpx.Response:
            return httpx.Response(200, content=b"")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: EmptyDeployClient())
    adapter = DokployAdapter("https://dokploy.example", "test-key")

    await adapter.deploy_application("application-1")
