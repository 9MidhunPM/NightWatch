import time

import pytest
from docker.errors import DockerException

from nightwatch.adapters.docker import DockerAdapter, DockerUnavailableError
from nightwatch.events.bus import EventBus
from nightwatch.services.docker_service import DockerService


@pytest.mark.anyio
async def test_docker_unavailable_does_not_crash_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DockerAdapter()

    def unavailable_client() -> object:
        raise DockerException("socket unavailable")

    monkeypatch.setattr(adapter, "_client", unavailable_client)
    service = DockerService(adapter, EventBus(4))

    status = await service.status()
    assert status.available is False
    assert status.container_count == 0
    with pytest.raises(DockerUnavailableError):
        await service.containers()


def test_usage_samples_running_containers_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Container:
        def __init__(self, identifier: str) -> None:
            self.id = identifier

        def stats(self, *, stream: bool) -> dict[str, object]:
            assert stream is False
            time.sleep(0.12)
            return {
                "cpu_stats": {"cpu_usage": {"total_usage": 2, "percpu_usage": [1]}, "system_cpu_usage": 2},
                "precpu_stats": {"cpu_usage": {"total_usage": 1}, "system_cpu_usage": 1},
                "memory_stats": {"usage": 10, "limit": 100},
                "networks": {},
            }

    class Containers:
        @staticmethod
        def list(*, all: bool) -> list[Container]:
            assert all is False
            return [Container(str(index)) for index in range(4)]

    class Client:
        containers = Containers()

        @staticmethod
        def ping() -> None:
            return None

    adapter = DockerAdapter()
    monkeypatch.setattr(adapter, "_client", lambda: Client())
    started = time.monotonic()
    usage = adapter.usage()
    assert len(usage) == 4
    assert time.monotonic() - started < 0.3
