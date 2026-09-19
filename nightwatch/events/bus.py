from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from nightwatch.events.models import RealtimeEvent

EventItem = RealtimeEvent | None


class EventBus:
    def __init__(self, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[EventItem]] = set()
        self._lock = asyncio.Lock()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[EventItem]]:
        queue: asyncio.Queue[EventItem] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def publish(self, event: RealtimeEvent) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers)
        overflowed: list[asyncio.Queue[EventItem]] = []
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                queue.get_nowait()
                queue.put_nowait(None)
                overflowed.append(queue)
        if overflowed:
            async with self._lock:
                for queue in overflowed:
                    self._subscribers.discard(queue)
