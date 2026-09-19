from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from nightwatch.models.docker_api import DockerContainer


class ContainerUsage(BaseModel):
    container_id: str
    cpu_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_limit_bytes: int | None = None
    memory_percent: float | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None
    observed_at: datetime
    available: bool = True
    message: str | None = None


class ResourceSnapshot(BaseModel):
    containers: list[DockerContainer] = Field(default_factory=list)
    usage: list[ContainerUsage] = Field(default_factory=list)
    observed_at: datetime


class AgentMessageRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class AgentCitation(BaseModel):
    resource_id: str
    source: str
    observed_at: datetime
    summary: str


class AgentFinding(BaseModel):
    label: str
    value: str
    detail: str | None = None


class AgentActivity(BaseModel):
    tool: str
    label: str
    status: str = "completed"
    detail: str | None = None
    arguments: dict[str, object] | None = None
    result: dict[str, object] | None = None


class AgentMessageResponse(BaseModel):
    answer: str
    findings: list[AgentFinding] = Field(default_factory=list)
    citations: list[AgentCitation] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    activity: list[AgentActivity] = Field(default_factory=list)
    pending_actions: list[dict[str, object]] = Field(default_factory=list)


class AgentStatusResponse(BaseModel):
    available: bool
    model: str | None = None
    message: str
    last_provider_success_at: datetime | None = None
    engine: str = "unavailable"
    tool_count: int = 0


class AgentConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime
    archived: bool = False


class AgentConversationDetail(AgentConversationSummary):
    turns: list[AgentConversationTurn] = Field(default_factory=list)
    pending_actions: list[dict[str, object]] = Field(default_factory=list)


class AgentConversationTurn(BaseModel):
    id: str
    role: str
    content: str
    activity: list[dict[str, object]] = Field(default_factory=list)
    findings: list[dict[str, object]] = Field(default_factory=list)
    citations: list[dict[str, object]] = Field(default_factory=list)
    created_at: datetime


class OperationsReport(BaseModel):
    generated_at: datetime
    host_summary: str
    container_count: int
    unhealthy_count: int
    active_incident_count: int
    resource_usage: list[ContainerUsage] = Field(default_factory=list)
