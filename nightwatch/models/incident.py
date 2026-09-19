from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nightwatch.storage.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(32), default="DETECTED")
    trigger: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    affected_resource_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    resource_id: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(512))
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IncidentTimelineEvent(Base):
    __tablename__ = "incident_timeline_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(512))
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    observation_id: Mapped[str | None] = mapped_column(ForeignKey("observations.id"), nullable=True)
    resource_id: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(512))
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), default="UNCONFIRMED")
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    contradicting_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_resource_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RepairPlan(Base):
    __tablename__ = "repair_plans"
    __table_args__ = (UniqueConstraint("incident_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    version: Mapped[int] = mapped_column(default=1)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="AWAITING_APPROVAL")
    target_resource_id: Mapped[str] = mapped_column(String(512))
    reason: Mapped[str] = mapped_column(String(1024))
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String(16))
    blast_radius_resource_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_downtime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_plan: Mapped[list[str]] = mapped_column(JSON, default=list)
    rollback_plan: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy_decision: Mapped[str] = mapped_column(String(32))
    policy_reason: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class RepairChange(Base):
    __tablename__ = "repair_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    repair_plan_id: Mapped[str] = mapped_column(ForeignKey("repair_plans.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(64))
    target_resource_id: Mapped[str] = mapped_column(String(512))
    field: Mapped[str] = mapped_column(String(255))
    from_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reversible: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    repair_plan_id: Mapped[str] = mapped_column(ForeignKey("repair_plans.id"), index=True)
    plan_version: Mapped[int] = mapped_column()
    decision: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ActionRecord(Base):
    __tablename__ = "action_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    repair_plan_id: Mapped[str] = mapped_column(ForeignKey("repair_plans.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(64))
    target_resource_id: Mapped[str] = mapped_column(String(512))
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    policy_decision: Mapped[str] = mapped_column(String(32))
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    rollback_state: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VerificationRun(Base):
    __tablename__ = "verification_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    action_record_id: Mapped[str] = mapped_column(ForeignKey("action_records.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationCheck(Base):
    __tablename__ = "verification_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    verification_run_id: Mapped[str] = mapped_column(ForeignKey("verification_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    observed: Mapped[str] = mapped_column(String(512))
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
