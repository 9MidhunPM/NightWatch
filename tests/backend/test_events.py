import pytest

from nightwatch.api.events import is_origin_allowed
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent


@pytest.mark.anyio
async def test_event_bus_delivers_typed_heartbeat_to_multiple_subscribers() -> None:
    bus = EventBus(queue_size=2)
    event = RealtimeEvent(payload={"source": "test"})

    async with bus.subscribe() as first, bus.subscribe() as second:
        await bus.publish(event)
        assert await first.get() == event
        assert await second.get() == event

    assert bus.subscriber_count == 0


@pytest.mark.anyio
async def test_slow_subscriber_is_disconnected_when_queue_overflows() -> None:
    bus = EventBus(queue_size=1)
    async with bus.subscribe() as queue:
        await bus.publish(RealtimeEvent(payload={"sequence": 1}))
        await bus.publish(RealtimeEvent(payload={"sequence": 2}))
        assert await queue.get() is None
        assert bus.subscriber_count == 0


def test_browser_origin_policy_is_explicit() -> None:
    allowed = ("http://127.0.0.1:3000",)
    assert is_origin_allowed("http://127.0.0.1:3000", allowed)
    assert not is_origin_allowed(None, allowed)
    assert not is_origin_allowed("https://untrusted.example", allowed)


def test_event_contract_accepts_declared_future_event_types() -> None:
    event = RealtimeEvent(type=EventType.TOPOLOGY_UPDATED, payload={"revision": 1})
    assert event.type == EventType.TOPOLOGY_UPDATED
