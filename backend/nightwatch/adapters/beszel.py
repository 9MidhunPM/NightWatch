from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class BeszelConnection:
    configured: bool
    available: bool
    message: str
    system_id: str | None = None


class BeszelAdapter:
    """Read-only connectivity check for Beszel's PocketBase-backed REST API."""

    def __init__(self, url: str | None, email: str | None, password: str | None, system_id: str | None) -> None:
        self._url = url.rstrip("/") if url else None
        self._email, self._password, self._system_id = email, password, system_id

    async def connection(self) -> BeszelConnection:
        if not all((self._url, self._email, self._password)):
            return BeszelConnection(False, False, "Beszel is not configured. Add a read-only user and hub URL in Dokploy.")
        assert self._url is not None
        try:
            async with httpx.AsyncClient(base_url=self._url, timeout=4.0) as client:
                auth = await client.post(
                    "/api/collections/users/auth-with-password",
                    json={"identity": self._email, "password": self._password},
                )
                auth.raise_for_status()
                token = str(auth.json().get("token") or "")
                if not token:
                    return BeszelConnection(True, False, "Beszel did not return an access token.")
                systems = await client.get(
                    "/api/collections/systems/records",
                    headers={"Authorization": token},
                    params={"perPage": 1, "filter": f"id='{self._system_id}'"} if self._system_id else {"perPage": 1},
                )
                systems.raise_for_status()
                items = systems.json().get("items") or []
                if not items:
                    return BeszelConnection(True, False, "The configured Beszel user cannot see the selected system.", self._system_id)
                return BeszelConnection(True, True, "Beszel is connected with read-only access.", str(items[0].get("id") or self._system_id))
        except httpx.HTTPError:
            return BeszelConnection(True, False, "Nightwatch could not reach Beszel with the configured read-only account.", self._system_id)
