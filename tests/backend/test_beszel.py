import asyncio

from nightwatch.adapters.beszel import BeszelAdapter


def test_beszel_history_normalizes_compact_system_stats():
    async def run():
        adapter = BeszelAdapter("https://beszel.example", "readonly@example.com", "password", "system-1")

        async def get(path, params):
            if path.endswith("systems/records"):
                return {"items": [{"id": "system-1", "info": {}}]}
            assert path.endswith("system_stats/records")
            assert "system='system-1'" in params["filter"]
            return {
                "items": [{
                    "created": "2026-09-20T10:00:00Z",
                    "stats": {"cpu": 12.5, "mp": 42.1, "mu": 3.5, "dp": 61, "nr": 4, "ns": 2},
                }]
            }

        adapter._get = get  # type: ignore[method-assign]
        series = await adapter.history("24h")
        assert series.available is True
        assert series.points[0].cpu_percent == 12.5
        assert series.points[0].memory_used_bytes == round(3.5 * 1024**3)
        assert series.points[0].network_rx_bytes == 4 * 1024**2

    asyncio.run(run())


def test_beszel_containers_expose_fresh_runtime_evidence():
    async def run():
        adapter = BeszelAdapter("https://beszel.example", "readonly@example.com", "password", "system-1")

        async def get(path, params):
            if path.endswith("systems/records"):
                return {"items": [{"id": "system-1", "info": {}}]}
            assert path.endswith("containers/records")
            assert "system='system-1'" in params["filter"]
            return {"items": [{
                "id": "container-1",
                "name": "/nightwatch-backend.1.task",
                "status": "Up 2 minutes",
                "health": 2,
                "cpu": 0.11,
                "memory": 306.4,
                "net": 786_000_000,
                "updated": "2026-09-20T10:00:00+00:00",
            }]}

        adapter._get = get  # type: ignore[method-assign]
        snapshot = await adapter.containers()
        assert snapshot.available is True
        assert snapshot.stale is False
        assert snapshot.containers[0].health == 2
        assert snapshot.containers[0].memory_used_bytes == round(306.4 * 1024**2)
        assert snapshot.containers[0].network_bytes == 786_000_000

    asyncio.run(run())
