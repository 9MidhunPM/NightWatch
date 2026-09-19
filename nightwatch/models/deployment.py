from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nightwatch.models.incident import utc_now
from nightwatch.storage.database import Base


class DeploymentPlan(Base):
    __tablename__ = "deployment_plans"
    __table_args__ = (UniqueConstraint("plan_digest"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(32), default="AWAITING_APPROVAL")
    owner: Mapped[str] = mapped_column(String(120))
    repository: Mapped[str] = mapped_column(String(160))
    branch: Mapped[str] = mapped_column(String(200))
    project_name: Mapped[str] = mapped_column(String(80))
    environment_name: Mapped[str] = mapped_column(String(80))
    service_name: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("agent_conversations.id"), nullable=True, index=True)
    build_type: Mapped[str] = mapped_column(String(32))
    build_path: Mapped[str] = mapped_column(String(300))
    dockerfile: Mapped[str | None] = mapped_column(String(300), nullable=True)
    port: Mapped[int] = mapped_column()
    domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    secret_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    manifest_notes: Mapped[str] = mapped_column(String(3000))
    plan_digest: Mapped[str] = mapped_column(String(64))
    policy_decision: Mapped[str] = mapped_column(String(32))
    policy_reason: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DeploymentApproval(Base):
    __tablename__ = "deployment_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deployment_plan_id: Mapped[str] = mapped_column(ForeignKey("deployment_plans.id"), index=True)
    plan_version: Mapped[int] = mapped_column()
    decision: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DeploymentExecution(Base):
    __tablename__ = "deployment_executions"
    __table_args__ = (UniqueConstraint("deployment_plan_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deployment_plan_id: Mapped[str] = mapped_column(ForeignKey("deployment_plans.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    project_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    environment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    application_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
