from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GithubRepository(BaseModel):
    owner: str
    name: str
    private: bool = False
    default_branch: str | None = None


class DeploymentPlanRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=120)
    repository: str = Field(min_length=1, max_length=160)
    branch: str = Field(min_length=1, max_length=200)
    project_name: str = Field(min_length=2, max_length=80)
    environment_name: str = Field(default="production", min_length=2, max_length=80)
    service_name: str = Field(min_length=2, max_length=80)
    build_type: Literal["dockerfile", "compose", "static"] = "dockerfile"
    build_path: str = Field(default="/", min_length=1, max_length=300)
    dockerfile: str | None = Field(default=None, max_length=300)
    port: int = Field(ge=1, le=65535)
    domain: str | None = Field(default=None, max_length=253)
    secret_names: list[str] = Field(default_factory=list, max_length=30)
    manifest_notes: str = Field(min_length=5, max_length=3000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class InferredDeploymentRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=120)
    repository: str = Field(min_length=1, max_length=160)
    project_name: str = Field(min_length=2, max_length=80)
    service_name: str = Field(min_length=2, max_length=80)
    domain: str = Field(min_length=3, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    environment_name: str = Field(default="production", min_length=2, max_length=80)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class DeploymentApprovalRequest(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED"]
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class DeploymentPlanResponse(BaseModel):
    id: str
    version: int
    status: str
    owner: str
    repository: str
    branch: str
    project_name: str
    environment_name: str
    service_name: str
    build_type: str
    build_path: str
    dockerfile: str | None
    port: int
    domain: str | None
    secret_names: list[str] = Field(default_factory=list)
    manifest_notes: str
    conversation_id: str | None = None
    plan_digest: str
    policy_decision: str
    policy_reason: str
    execution_status: str | None = None
    execution_detail: str | None = None
    created_at: datetime
    updated_at: datetime


class DeploymentStatusResponse(BaseModel):
    configured: bool
    github_provider_configured: bool
    app_server_enabled: bool
    message: str
    provider_name: str | None = None
    repository_count: int | None = None
    last_checked_at: datetime | None = None
    diagnostic_code: str | None = None
