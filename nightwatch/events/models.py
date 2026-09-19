from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    SYSTEM_HEARTBEAT = "SYSTEM_HEARTBEAT"
    HOST_UPDATED = "HOST_UPDATED"
    TOPOLOGY_UPDATED = "TOPOLOGY_UPDATED"
    INCIDENT_CREATED = "INCIDENT_CREATED"
    INCIDENT_UPDATED = "INCIDENT_UPDATED"
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    ROOT_CAUSE_CONFIRMED = "ROOT_CAUSE_CONFIRMED"
    REPAIR_PLANNED = "REPAIR_PLANNED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ACTION_STARTED = "ACTION_STARTED"
    ACTION_FAILED = "ACTION_FAILED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"


class RealtimeEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: EventType = EventType.SYSTEM_HEARTBEAT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    server_id: str | None = None
    incident_id: str | None = None
    resource_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
