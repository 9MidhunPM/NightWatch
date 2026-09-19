from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    retryable: bool
    request_id: str
    timestamp: datetime
