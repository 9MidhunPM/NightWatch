from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nightwatch.models.incident import utc_now
from nightwatch.storage.database import Base


class ProjectPlan(Base):
    __tablename__ = "project_plans"
    __table_args__ = (UniqueConstraint("project_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version: Mapped[int] = mapped_column(default=1)
    project_name: Mapped[str] = mapped_column(String(80))
    environment_name: Mapped[str] = mapped_column(String(80), default="production")
    service_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("agent_conversations.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="AWAITING_APPROVAL")
    policy_reason: Mapped[str] = mapped_column(String(512))
    detail: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
