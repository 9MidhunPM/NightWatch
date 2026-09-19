from datetime import UTC, datetime

from pydantic import BaseModel, Field


class RealtimeEvent(BaseModel):
    type: str = "heartbeat"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, object] = Field(default_factory=dict)
