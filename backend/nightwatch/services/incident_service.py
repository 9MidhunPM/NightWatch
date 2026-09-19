from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.incident import (
    ActionRecord,
    Approval,
    Evidence,
    Hypothesis,
    Incident,
    IncidentTimelineEvent,
    Observation,
    RepairChange,
    RepairPlan,
    VerificationCheck,
    VerificationRun,
)
from nightwatch.models.incident_api import (
    ActionRecordResponse,
    ApprovalResponse,
    EvidenceResponse,
    HypothesisResponse,
    IncidentResponse,
    ObservationResponse,
    RepairChangeResponse,
    RepairPlanResponse,
    TimelineEventResponse,
    VerificationCheckResponse,
    VerificationRunResponse,
)
from nightwatch.models.topology_api import TopologySnapshot
from nightwatch.security.redaction import redact

_OPEN_STATES = {"DETECTED", "INVESTIGATING", "HUMAN_REQUIRED", "ROOT_CAUSE_CONFIRMED", "VERIFYING", "VERIFICATION_FAILED"}


class IncidentService:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], event_bus: EventBus
    ) -> None:
        self._session_factory = session_factory
        self._event_bus = event_bus

    async def report_failure(
        self,
        *,
        key: str,
        title: str,
        severity: str,
        trigger: dict[str, object],
        affected_resource_ids: list[str],
        observation_summary: str,
        observation_data: dict[str, object],
    ) -> IncidentResponse:
        async with self._session_factory() as session:
            incident = await self._open_for_key(session, key)
            created = incident is None
            if incident is None:
                incident = Incident(
                    title=title,
                    severity=severity,
                    state="DETECTED",
                    trigger=redact({**trigger, "key": key}),
                    affected_resource_ids=affected_resource_ids,
                )
                session.add(incident)
                await session.flush()
                self._timeline(session, incident.id, "INCIDENT_DETECTED", title, trigger)
                self._observation(
                    session,
                    incident.id,
                    affected_resource_ids[0] if affected_resource_ids else key,
                    observation_summary,
                    redact(observation_data),
                )
            await session.commit()
            response = await self._detail(session, incident.id)
            assert response is not None
        if created:
            await self._event_bus.publish(
                RealtimeEvent(
                    type=EventType.INCIDENT_CREATED,
                    incident_id=response.id,
                    resource_id=response.affected_resource_ids[0]
                    if response.affected_resource_ids
                    else None,
                    payload={"title": response.title, "severity": response.severity},
                )
            )
            await self._event_bus.publish(
                RealtimeEvent(
                    type=EventType.OBSERVATION_ADDED,
                    incident_id=response.id,
                    resource_id=response.affected_resource_ids[0]
                    if response.affected_resource_ids
                    else None,
                    payload={"summary": observation_summary},
                )
            )
        return response

    async def report_recovery(self, key: str, summary: str) -> IncidentResponse | None:
        async with self._session_factory() as session:
            incident = await self._open_for_key(session, key)
            if incident is None:
                return None
            incident.state = "RECOVERED_EXTERNALLY"
            incident.updated_at = datetime.now(UTC)
            self._timeline(session, incident.id, "SYMPTOM_RECOVERED", summary, {})
            self._observation(session, incident.id, incident.affected_resource_ids[0], summary, {})
            await session.commit()
            response = await self._detail(session, incident.id)
            assert response is not None
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.INCIDENT_UPDATED,
                incident_id=response.id,
                payload={"state": response.state},
            )
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.OBSERVATION_ADDED,
                incident_id=response.id,
                resource_id=response.affected_resource_ids[0]
                if response.affected_resource_ids
                else None,
                payload={"summary": summary},
            )
        )
        return response

    async def list_incidents(self) -> list[IncidentResponse]:
        async with self._session_factory() as session:
            incidents = list(
                (
                    await session.scalars(
                        select(Incident).order_by(Incident.updated_at.desc()).limit(30)
                    )
                ).all()
            )
            responses = [await self._detail(session, incident.id) for incident in incidents]
            return [response for response in responses if response is not None]

    async def get_incident(self, incident_id: str) -> IncidentResponse | None:
        async with self._session_factory() as session:
            return await self._detail(session, incident_id)

    async def begin_investigation(self, incident_id: str) -> IncidentResponse | None:
        async with self._session_factory() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None or incident.state not in {"DETECTED", "HUMAN_REQUIRED"}:
                return None
            restarting = incident.state == "HUMAN_REQUIRED"
            incident.state = "INVESTIGATING"
            incident.updated_at = datetime.now(UTC)
            self._timeline(
                session,
                incident.id,
                "INVESTIGATION_RESTARTED" if restarting else "INVESTIGATION_STARTED",
                "Investigator started read-only evidence collection.",
                {},
            )
            await session.commit()
            response = await self._detail(session, incident_id)
            assert response is not None
        await self._event_bus.publish(
            RealtimeEvent(type=EventType.INVESTIGATION_STARTED, incident_id=incident_id)
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.INCIDENT_UPDATED,
                incident_id=incident_id,
                payload={"state": response.state},
            )
        )
        return response

    async def record_tool_evidence(
        self,
        incident_id: str,
        *,
        tool: str,
        resource_id: str,
        summary: str,
        data: dict[str, object],
        usable: bool,
    ) -> str | None:
        async with self._session_factory() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None or incident.state != "INVESTIGATING":
                return None
            safe_data = {**redact(data), "_usable": usable}
            observation = Observation(
                incident_id=incident_id,
                resource_id=resource_id,
                source=tool,
                summary=summary,
                data=safe_data,
            )
            session.add(observation)
            await session.flush()
            evidence = Evidence(
                incident_id=incident_id,
                observation_id=observation.id,
                resource_id=resource_id,
                source=tool,
                summary=summary,
                data=safe_data,
            )
            session.add(evidence)
            self._timeline(
                session,
                incident_id,
                "TOOL_COMPLETED",
                summary,
                {"tool": tool, "resource_id": resource_id},
            )
            await session.commit()
            evidence_id = evidence.id
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.TOOL_COMPLETED,
                incident_id=incident_id,
                resource_id=resource_id,
                payload={"tool": tool, "summary": summary},
            )
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.OBSERVATION_ADDED,
                incident_id=incident_id,
                resource_id=resource_id,
                payload={"summary": summary},
            )
        )
        return evidence_id

    async def record_tool_started(self, incident_id: str, tool: str) -> None:
        async with self._session_factory() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None or incident.state != "INVESTIGATING":
                return
            self._timeline(session, incident_id, "TOOL_STARTED", f"Running {tool}.", {"tool": tool})
            await session.commit()
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.TOOL_STARTED, incident_id=incident_id, payload={"tool": tool}
            )
        )

    async def apply_investigation_outcome(
        self,
        incident_id: str,
        *,
        summary: str,
        hypotheses: list[dict[str, object]],
        confirmed_title: str | None,
        next_step: str,
    ) -> IncidentResponse | None:
        async with self._session_factory() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None or incident.state != "INVESTIGATING":
                return None
            evidence_rows = list(
                (
                    await session.scalars(
                        select(Evidence).where(Evidence.incident_id == incident_id)
                    )
                ).all()
            )
            evidence_ids = {item.id for item in evidence_rows}
            usable_evidence_ids = {
                item.id for item in evidence_rows if item.data.get("_usable") is True
            }
            persisted: list[Hypothesis] = []
            for item in hypotheses[:4]:
                title = item.get("title")
                description = item.get("description")
                status = item.get("status")
                if (
                    not isinstance(title, str)
                    or not isinstance(description, str)
                    or status not in {"UNCONFIRMED", "SUPPORTED", "CONFIRMED", "DISPROVED"}
                ):
                    continue
                supporting = [
                    item_id
                    for item_id in self._string_list(item.get("supporting_evidence_ids"))
                    if item_id in usable_evidence_ids
                ]
                contradicting = [
                    item_id
                    for item_id in self._string_list(item.get("contradicting_evidence_ids"))
                    if item_id in evidence_ids
                ]
                related = self._string_list(item.get("related_resource_ids"))[:12]
                if status == "CONFIRMED" and not supporting:
                    status = "SUPPORTED" if supporting else "UNCONFIRMED"
                hypothesis = Hypothesis(
                    incident_id=incident_id,
                    title=title[:255],
                    description=description[:1024],
                    status=status,
                    supporting_evidence_ids=supporting,
                    contradicting_evidence_ids=contradicting,
                    related_resource_ids=related,
                )
                session.add(hypothesis)
                persisted.append(hypothesis)
            await session.flush()
            confirmed = next(
                (
                    item
                    for item in persisted
                    if item.title == confirmed_title
                    and item.status == "CONFIRMED"
                    and item.supporting_evidence_ids
                ),
                None,
            )
            competing_supported = any(
                item.status == "SUPPORTED" and item is not confirmed for item in persisted
            )
            if confirmed and not competing_supported:
                incident.state = "ROOT_CAUSE_CONFIRMED"
                self._timeline(
                    session,
                    incident_id,
                    "ROOT_CAUSE_CONFIRMED",
                    f"Root cause confirmed: {confirmed.title}",
                    {"hypothesis_id": confirmed.id, "next_step": next_step[:512]},
                )
            else:
                incident.state = "HUMAN_REQUIRED"
                self._timeline(
                    session,
                    incident_id,
                    "INVESTIGATION_INCOMPLETE",
                    summary[:512],
                    {"next_step": next_step[:512]},
                )
            incident.updated_at = datetime.now(UTC)
            await session.commit()
            response = await self._detail(session, incident_id)
            assert response is not None
        for result_hypothesis in response.hypotheses:
            event = (
                EventType.HYPOTHESIS_DISPROVED
                if result_hypothesis.status == "DISPROVED"
                else EventType.HYPOTHESIS_CREATED
            )
            await self._event_bus.publish(
                RealtimeEvent(
                    type=event,
                    incident_id=incident_id,
                    payload={"title": result_hypothesis.title, "status": result_hypothesis.status},
                )
            )
        terminal_event = (
            EventType.ROOT_CAUSE_CONFIRMED
            if response.state == "ROOT_CAUSE_CONFIRMED"
            else EventType.INVESTIGATION_FAILED
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=terminal_event, incident_id=incident_id, payload={"summary": summary[:512]}
            )
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.INCIDENT_UPDATED,
                incident_id=incident_id,
                payload={"state": response.state},
            )
        )
        return response

    async def investigation_failed(self, incident_id: str, summary: str) -> IncidentResponse | None:
        async with self._session_factory() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None or incident.state != "INVESTIGATING":
                return None
            incident.state = "HUMAN_REQUIRED"
            incident.updated_at = datetime.now(UTC)
            self._timeline(session, incident_id, "INVESTIGATION_FAILED", summary[:512], {})
            await session.commit()
            response = await self._detail(session, incident_id)
            assert response is not None
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.INVESTIGATION_FAILED,
                incident_id=incident_id,
                payload={"summary": summary[:512]},
            )
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.INCIDENT_UPDATED,
                incident_id=incident_id,
                payload={"state": response.state},
            )
        )
        return response

    async def record_repair_plan(
        self,
        incident_id: str,
        *,
        plan_id: str,
        title: str,
        target_resource_id: str,
        policy_decision: str,
        policy_reason: str,
    ) -> None:
        """Append the auditable planning events; no approval or execution occurs here."""
        async with self._session_factory() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None:
                return
            self._timeline(
                session,
                incident_id,
                "REPAIR_PLANNED",
                title,
                {"repair_plan_id": plan_id, "target_resource_id": target_resource_id},
            )
            self._timeline(
                session,
                incident_id,
                "POLICY_DECIDED",
                policy_reason,
                {"repair_plan_id": plan_id, "decision": policy_decision},
            )
            self._timeline(
                session,
                incident_id,
                "APPROVAL_REQUIRED",
                "Human approval is required before Nightwatch can execute this plan.",
                {"repair_plan_id": plan_id},
            )
            incident.updated_at = datetime.now(UTC)
            await session.commit()
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.REPAIR_PLANNED,
                incident_id=incident_id,
                resource_id=target_resource_id,
                payload={"repair_plan_id": plan_id, "title": title},
            )
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.POLICY_DECIDED,
                incident_id=incident_id,
                payload={"repair_plan_id": plan_id, "decision": policy_decision},
            )
        )
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.APPROVAL_REQUIRED,
                incident_id=incident_id,
                payload={"repair_plan_id": plan_id},
            )
        )

    async def record_approval(
        self, plan_id: str, *, plan_version: int, decision: str, actor: str
    ) -> IncidentResponse | None:
        """Record a version-bound operator decision; this never executes a repair."""
        async with self._session_factory() as session:
            plan = await session.get(RepairPlan, plan_id)
            if (
                plan is None
                or plan.version != plan_version
                or plan.status != "AWAITING_APPROVAL"
                or decision not in {"APPROVED", "REJECTED"}
            ):
                return None
            session.add(
                Approval(
                    repair_plan_id=plan.id,
                    plan_version=plan.version,
                    decision=decision,
                    actor=actor,
                )
            )
            plan.status = decision
            self._timeline(
                session,
                plan.incident_id,
                "APPROVAL_UPDATED",
                f"Operator {decision.lower()} repair plan v{plan.version}.",
                {"repair_plan_id": plan.id, "plan_version": plan.version, "decision": decision},
            )
            await session.commit()
            response = await self._detail(session, plan.incident_id)
            assert response is not None
        await self._event_bus.publish(
            RealtimeEvent(
                type=EventType.APPROVAL_UPDATED,
                incident_id=response.id,
                payload={"repair_plan_id": plan_id, "decision": decision, "plan_version": plan_version},
            )
        )
        return response

    async def overlay_health(self, snapshot: TopologySnapshot) -> TopologySnapshot:
        active = [
            incident for incident in await self.list_incidents() if incident.state in _OPEN_STATES
        ]
        affected = {
            resource_id for incident in active for resource_id in incident.affected_resource_ids
        }
        for node in snapshot.nodes:
            if node.id in affected:
                node.health = "UNHEALTHY"
        for edge in snapshot.edges:
            if edge.id in affected:
                edge.health = "UNHEALTHY"
        return snapshot

    async def _open_for_key(self, session: AsyncSession, key: str) -> Incident | None:
        incidents = list(
            (await session.scalars(select(Incident).order_by(Incident.updated_at.desc()))).all()
        )
        return next(
            (
                incident
                for incident in incidents
                if incident.state in _OPEN_STATES and incident.trigger.get("key") == key
            ),
            None,
        )

    async def _detail(self, session: AsyncSession, incident_id: str) -> IncidentResponse | None:
        incident = await session.get(Incident, incident_id)
        if incident is None:
            return None
        observations = list(
            (
                await session.scalars(
                    select(Observation)
                    .where(Observation.incident_id == incident_id)
                    .order_by(Observation.created_at)
                )
            ).all()
        )
        evidence = list(
            (
                await session.scalars(
                    select(Evidence)
                    .where(Evidence.incident_id == incident_id)
                    .order_by(Evidence.created_at)
                )
            ).all()
        )
        hypotheses = list(
            (
                await session.scalars(
                    select(Hypothesis)
                    .where(Hypothesis.incident_id == incident_id)
                    .order_by(Hypothesis.created_at)
                )
            ).all()
        )
        timeline = list(
            (
                await session.scalars(
                    select(IncidentTimelineEvent)
                    .where(IncidentTimelineEvent.incident_id == incident_id)
                    .order_by(IncidentTimelineEvent.created_at)
                )
            ).all()
        )
        repair_plan = await session.scalar(
            select(RepairPlan)
            .where(RepairPlan.incident_id == incident_id)
            .order_by(RepairPlan.version.desc(), RepairPlan.created_at.desc())
            .limit(1)
        )
        changes: list[RepairChange] = []
        approvals: list[Approval] = []
        if repair_plan is not None:
            changes = list(
                (
                    await session.scalars(
                        select(RepairChange)
                        .where(RepairChange.repair_plan_id == repair_plan.id)
                        .order_by(RepairChange.created_at)
                    )
                ).all()
            )
            approvals = list(
                (
                    await session.scalars(
                        select(Approval)
                        .where(Approval.repair_plan_id == repair_plan.id)
                        .order_by(Approval.created_at)
                    )
                ).all()
            )
        actions = list((await session.scalars(
            select(ActionRecord).where(ActionRecord.incident_id == incident_id).order_by(ActionRecord.created_at)
        )).all())
        action_responses: list[ActionRecordResponse] = []
        for action in actions:
            run = await session.scalar(select(VerificationRun).where(VerificationRun.action_record_id == action.id).order_by(VerificationRun.started_at.desc()).limit(1))
            verification = None
            if run is not None:
                checks = list((await session.scalars(select(VerificationCheck).where(VerificationCheck.verification_run_id == run.id).order_by(VerificationCheck.created_at))).all())
                verification = VerificationRunResponse(
                    **VerificationRunResponse.model_validate(run, from_attributes=True).model_dump(exclude={"checks"}),
                    checks=[VerificationCheckResponse.model_validate(item, from_attributes=True) for item in checks],
                )
            action_responses.append(ActionRecordResponse(
                **ActionRecordResponse.model_validate(action, from_attributes=True).model_dump(exclude={"verification"}),
                verification=verification,
            ))
        return IncidentResponse(
            id=incident.id,
            title=incident.title,
            severity=incident.severity,
            state=incident.state,
            trigger=incident.trigger,
            affected_resource_ids=incident.affected_resource_ids,
            detected_at=incident.detected_at,
            resolved_at=incident.resolved_at,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            observations=[
                ObservationResponse.model_validate(item, from_attributes=True)
                for item in observations
            ],
            timeline=[
                TimelineEventResponse.model_validate(item, from_attributes=True)
                for item in timeline
            ],
            evidence=[
                EvidenceResponse.model_validate(item, from_attributes=True) for item in evidence
            ],
            hypotheses=[
                HypothesisResponse.model_validate(item, from_attributes=True) for item in hypotheses
            ],
            repair_plan=(
                RepairPlanResponse(
                    **RepairPlanResponse.model_validate(
                        repair_plan, from_attributes=True
                    ).model_dump(exclude={"changes", "approvals"}),
                    changes=[
                        RepairChangeResponse.model_validate(item, from_attributes=True)
                        for item in changes
                    ],
                    approvals=[
                        ApprovalResponse.model_validate(item, from_attributes=True)
                        for item in approvals
                    ],
                )
                if repair_plan is not None
                else None
            ),
            actions=action_responses,
        )

    @staticmethod
    def _timeline(
        session: AsyncSession,
        incident_id: str,
        event_type: str,
        summary: str,
        data: dict[str, object],
    ) -> None:
        session.add(
            IncidentTimelineEvent(
                incident_id=incident_id, event_type=event_type, summary=summary, data=data
            )
        )

    @staticmethod
    def _observation(
        session: AsyncSession,
        incident_id: str,
        resource_id: str,
        summary: str,
        data: dict[str, object],
    ) -> None:
        session.add(
            Observation(
                incident_id=incident_id,
                resource_id=resource_id,
                source="monitoring",
                summary=summary,
                data=redact(data),
            )
        )

    @staticmethod
    def _string_list(value: object) -> list[str]:
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
