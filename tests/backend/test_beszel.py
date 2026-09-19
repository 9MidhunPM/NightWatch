import asyncio

from nightwatch.adapters.beszel import BeszelAdapter


def test_beszel_history_normalizes_compact_system_stats():
    async def run():
        adapter = BeszelAdapter("https://beszel.example", "readonly@example.com", "password", "system-1")

        async def get(path, params):
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
