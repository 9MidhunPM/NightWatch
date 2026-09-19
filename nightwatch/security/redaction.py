from __future__ import annotations

import re
from typing import Any

_SECRET_KEY = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|private[_-]?key)", re.IGNORECASE
)
_URL_CREDENTIALS = re.compile(r"(://[^:/\s]+:)[^@/\s]+@")
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*(?:PASS(?:WORD)?|SECRET|TOKEN|API[_-]?KEY|COOKIE)[A-Za-z0-9_]*)=([^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_QUERY = re.compile(
    r"([?&](?:pass(?:word)?|secret|token|api[_-]?key|authorization|cookie)=)[^&#\s]+", re.IGNORECASE
)


def redact(value: Any) -> Any:
    """Return a structurally equivalent value with common secret shapes removed."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        safe = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
        safe = _SECRET_QUERY.sub(r"\1[REDACTED]", safe)
        safe = _SECRET_ASSIGNMENT.sub(r"\1=[REDACTED]", safe)
        return _BEARER.sub("Bearer [REDACTED]", safe)
    return value
