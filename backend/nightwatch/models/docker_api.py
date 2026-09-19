from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DockerPort(BaseModel):
    internal: str
    host_ip: str | None = None
    host_port: int | None = None


class DockerContainer(BaseModel):
    id: str
    name: str
    image: str
    state: str
    health: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    restart_count: int = 0
    ports: list[DockerPort] = Field(default_factory=list)
    networks: list[str] = Field(default_factory=list)
    restart_policy: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    compose_project: str | None = None
    compose_service: str | None = None
    resource_type: str = "CONTAINER"


class DockerNetworkMember(BaseModel):
    id: str
    name: str


class DockerNetwork(BaseModel):
    id: str
    name: str
    driver: str
    internal: bool
    containers: list[DockerNetworkMember] = Field(default_factory=list)


class DockerInventory(BaseModel):
    available: bool
    message: str | None = None
    discovered_at: datetime
    containers: list[DockerContainer] = Field(default_factory=list)
    networks: list[DockerNetwork] = Field(default_factory=list)


class DockerStatus(BaseModel):
    available: bool
    message: str | None = None
    discovered_at: datetime
    container_count: int = 0
    running_count: int = 0
    unhealthy_count: int = 0
