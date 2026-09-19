from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal[
    "HOST",
    "CONTAINER",
    "SERVICE",
    "DATABASE",
    "CACHE",
    "REVERSE_PROXY",
    "ROUTE",
    "DOMAIN",
    "NETWORK",
    "INTERNET",
]
EdgeType = Literal["RUNS_ON", "MEMBER_OF", "ROUTES_TO", "EXPOSES", "CONNECTS_TO", "DEPENDS_ON"]
HealthState = Literal["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN", "CHANGING"]


class InfrastructureNode(BaseModel):
    id: str
    type: NodeType
    label: str
    health: HealthState
    detail: str | None = None
    protected: bool = False
    attributes: dict[str, str] = Field(default_factory=dict)


class InfrastructureEdge(BaseModel):
    id: str
    source: str
    target: str
    type: EdgeType
    health: HealthState = "UNKNOWN"
    provenance: str
    detail: str | None = None


class TopologySnapshot(BaseModel):
    available: bool
    message: str | None = None
    generated_at: datetime
    nodes: list[InfrastructureNode] = Field(default_factory=list)
    edges: list[InfrastructureEdge] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
