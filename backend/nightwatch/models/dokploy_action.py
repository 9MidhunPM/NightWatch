from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nightwatch.models.incident import utc_now
from nightwatch.storage.database import Base


class DokployActionPlan(Base):
    __tablename__ = "dokploy_action_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(32), default="AWAITING_APPROVAL")
    action: Mapped[str] = mapped_column(String(80))
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(160))
    target_name: Mapped[str] = mapped_column(String(160))
    project_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    expected_state: Mapped[str] = mapped_column(Text())
    request_digest: Mapped[str] = mapped_column(String(64), unique=True)
    policy_reason: Mapped[str] = mapped_column(String(512))
    detail: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("agent_conversations.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
