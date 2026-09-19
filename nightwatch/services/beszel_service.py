from __future__ import annotations

from nightwatch.adapters.beszel import BeszelAdapter, BeszelConnection


class BeszelService:
    def __init__(self, adapter: BeszelAdapter) -> None:
        self._adapter = adapter

    async def connection(self) -> BeszelConnection:
        return await self._adapter.connection()
