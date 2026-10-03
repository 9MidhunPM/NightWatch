import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

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


@pytest.mark.parametrize(
    ("sample_age_seconds", "expected_stale"),
    [(0, False), (69.999, False), (70, False), (70.001, True), (315_360_000, True)],
)
def test_beszel_containers_expose_runtime_evidence(sample_age_seconds, expected_stale):
    observed_at = datetime(2026, 9, 20, 10, tzinfo=UTC)

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
                "updated": observed_at.isoformat(),
            }]}

        adapter._get = get  # type: ignore[method-assign]
        # Freeze the clock so freshness is independent of the date CI runs.
        with patch("nightwatch.adapters.beszel.datetime", wraps=datetime) as clock:
            clock.now.return_value = observed_at + timedelta(seconds=sample_age_seconds)
            snapshot = await adapter.containers()
        assert snapshot.available is True
        assert snapshot.stale is expected_stale
        assert snapshot.observed_at == observed_at
        assert snapshot.containers[0].stale is expected_stale
        assert snapshot.containers[0].observed_at == observed_at
        assert snapshot.containers[0].health == 2
        assert snapshot.containers[0].memory_used_bytes == round(306.4 * 1024**2)
        assert snapshot.containers[0].network_bytes == 786_000_000

    asyncio.run(run())
