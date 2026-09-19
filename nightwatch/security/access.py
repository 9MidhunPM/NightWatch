from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field


def valid_frontend_token(provided: str | None, expected: str | None) -> bool:
    return bool(provided and expected and hmac.compare_digest(provided, expected))


def issue_realtime_ticket(secret: str, lifetime_seconds: int) -> tuple[str, str, int]:
    expires_at = int(time.time()) + lifetime_seconds
    nonce = secrets.token_urlsafe(12)
    encoded = base64.urlsafe_b64encode(
        json.dumps({"exp": expires_at, "nonce": nonce}, separators=(",", ":")).encode()
    ).rstrip(b"=")
    signature = hmac.new(secret.encode(), encoded, hashlib.sha256).digest()
    return (
        f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}",
        nonce,
        expires_at,
    )


def ticket_nonce(ticket: str | None, secret: str | None) -> tuple[str, int] | None:
    if not ticket or not secret or "." not in ticket:
        return None
    encoded, supplied_signature = ticket.rsplit(".", 1)
    expected_signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    nonce, expires_at = payload.get("nonce"), payload.get("exp")
    if not isinstance(nonce, str) or not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None
    return nonce, expires_at


@dataclass
class RealtimeTicketRegistry:
    _issued: dict[str, int] = field(default_factory=dict)

    def issue(self, secret: str, lifetime_seconds: int) -> str:
        ticket, nonce, expires_at = issue_realtime_ticket(secret, lifetime_seconds)
        now = int(time.time())
        self._issued = {key: expiry for key, expiry in self._issued.items() if expiry >= now}
        self._issued[nonce] = expires_at
        return ticket

    def consume(self, ticket: str | None, secret: str | None) -> bool:
        verified = ticket_nonce(ticket, secret)
        if verified is None:
            return False
        nonce, expires_at = verified
        stored_expiry = self._issued.pop(nonce, None)
        return stored_expiry == expires_at and stored_expiry >= int(time.time())
