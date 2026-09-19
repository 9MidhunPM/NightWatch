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


class EvidenceStatus(BaseModel):
    source: str
    observed_at: datetime | None = None
    state: str = "unavailable"
    message: str | None = None


class ReplicaState(BaseModel):
    running: int = 0
    desired: int | None = None


class ResourceMetrics(BaseModel):
    cpu_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_limit_bytes: int | None = None
    memory_percent: float | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None
    block_read_bytes: int | None = None
    block_write_bytes: int | None = None
    restart_count: int | None = None
    observed_at: datetime | None = None
    source: str = "unavailable"
    stale: bool = False


class HostMetrics(BaseModel):
    cpu_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None
    memory_percent: float | None = None
    disk_used_bytes: int | None = None
    disk_total_bytes: int | None = None
    disk_percent: float | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None
    load_1m: float | None = None
    observed_at: datetime | None = None
    source: str = "unavailable"
    stale: bool = False


class DeploymentSummary(BaseModel):
    id: str
    title: str
    status: str
    commit: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class WorldResource(BaseModel):
    id: str
    name: str
    kind: str
    project_id: str
    environment: str
    app_name: str = ""
    compose_service: str | None = None
    owner: str | None = None
    repository: str | None = None
    branch: str | None = None
    build_type: str | None = None
    build_path: str | None = None
    dockerfile: str | None = None
    image: str | None = None
    auto_deploy: bool | None = None
    declared_dependencies: list[str] = Field(default_factory=list)
    deployment_state: str = "unknown"
    runtime_state: str = "unknown"
    health: str = "UNKNOWN"
    container_ids: list[str] = Field(default_factory=list)
    networks: list[str] = Field(default_factory=list)
    replicas: ReplicaState | None = None
    metrics: ResourceMetrics | None = None
    recent_deployments: list[DeploymentSummary] = Field(default_factory=list)
    evidence: list[EvidenceStatus] = Field(default_factory=list)
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
    coverage: float = 0.0
    host_metrics: HostMetrics | None = None
    projects: list[WorldProject] = Field(default_factory=list)
    connections: list[WorldConnection] = Field(default_factory=list)
    message: str | None = None
