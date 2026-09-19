from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nightwatch.storage.database import Base


class WorldState(Base):
    __tablename__ = "world_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class DomainCheck(BaseModel):
    url: str
    target_service: str | None = None
    state: str = "UNKNOWN"
    status_code: int | None = None
    latency_ms: int | None = None
    message: str = "Not checked yet"
    checked_at: datetime | None = None
    failures: int = 0
    successes: int = 0
    incident_id: str | None = None


class WorldResource(BaseModel):
    id: str
    name: str
    kind: str
    project_id: str
    environment: str
    app_name: str = ""
    compose_service: str | None = None
    declared_dependencies: list[str] = Field(default_factory=list)
    deployment_state: str = "unknown"
    runtime_state: str = "unknown"
    health: str = "UNKNOWN"
    container_ids: list[str] = Field(default_factory=list)
    networks: list[str] = Field(default_factory=list)
    domains: list[DomainCheck] = Field(default_factory=list)
    observed_at: datetime | None = None


class WorldProject(BaseModel):
    id: str
    name: str
    environments: list[str] = Field(default_factory=list)
    health: str = "UNKNOWN"
    resources: list[WorldResource] = Field(default_factory=list)


class WorldConnection(BaseModel):
    id: str
    source: str
    target: str
    kind: str
    provenance: str


class WorldSnapshot(BaseModel):
    generated_at: datetime
    inventory_at: datetime | None = None
    stale: bool = True
    sources: dict[str, str] = Field(default_factory=dict)
    projects: list[WorldProject] = Field(default_factory=list)
    connections: list[WorldConnection] = Field(default_factory=list)
    message: str | None = None
