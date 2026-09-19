from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ObservationResponse(BaseModel):
    id: str
    resource_id: str
    source: str
    summary: str
    data: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class TimelineEventResponse(BaseModel):
    id: str
    event_type: str
    summary: str
    data: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class EvidenceResponse(BaseModel):
    id: str
    observation_id: str | None
    resource_id: str
    source: str
    summary: str
    data: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class HypothesisResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    related_resource_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RepairChangeResponse(BaseModel):
    id: str
    action_type: str
    target_resource_id: str
    field: str
    from_value: str | None
    to_value: str | None
    reversible: bool


class ApprovalResponse(BaseModel):
    id: str
    plan_version: int
    decision: str
    actor: str
    created_at: datetime


class ApprovalRequest(BaseModel):
    plan_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED"]


class VerificationCheckResponse(BaseModel):
    id: str
    name: str
    status: str
    observed: str
    evidence: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class VerificationRunResponse(BaseModel):
    id: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    checks: list[VerificationCheckResponse] = Field(default_factory=list)


class ActionRecordResponse(BaseModel):
    id: str
    action_type: str
    target_resource_id: str
    status: str
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    verification: VerificationRunResponse | None = None


class RepairPlanResponse(BaseModel):
    id: str
    version: int
    title: str
    status: str
    target_resource_id: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    risk_level: str
    blast_radius_resource_ids: list[str] = Field(default_factory=list)
    expected_downtime: str | None
    verification_plan: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    policy_decision: str
    policy_reason: str
    changes: list[RepairChangeResponse] = Field(default_factory=list)
    approvals: list[ApprovalResponse] = Field(default_factory=list)
    approval_action_available: bool = False
    created_at: datetime
    updated_at: datetime


class IncidentResponse(BaseModel):
    id: str
    title: str
    severity: str
    state: str
    trigger: dict[str, object]
    affected_resource_ids: list[str]
    detected_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    observations: list[ObservationResponse] = Field(default_factory=list)
    timeline: list[TimelineEventResponse] = Field(default_factory=list)
    evidence: list[EvidenceResponse] = Field(default_factory=list)
    hypotheses: list[HypothesisResponse] = Field(default_factory=list)
    repair_plan: RepairPlanResponse | None = None
    actions: list[ActionRecordResponse] = Field(default_factory=list)
